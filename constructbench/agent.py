"""`ci:<model>[@url]` — the Constructelligence small-model agent: a local model plus a harness that plays to its strengths.

A 1–8B model reads a construction scenario well and does multi-step arithmetic badly (qwen2.5-1.5b: 0/41 strict on the
quick set as a plain chat model, 44% of replies without the required ANSWER line). The same idea that lifted it on
AEC-Bench (local-qwen small_model adapter, 0.81 → 0.87 held-out) applies here:

1. The answer's shape comes from the prompt's own "Answer keys:" line — names and types. The agent never looks at
   task.answer or task.fields (the grader's side).
2. The model writes a short Python program: every given quantity as a named variable, each step as a line, and a final
   print of the answer dict. The agent runs it (a stripped-down interpreter: math/statistics/fractions/itertools/
   datetime only, no files, no network, 10 s) and feeds any error or missing key back for a bounded retry.
3. Several programs are sampled and each field is decided by vote, so one slip in one program does not decide it.
4. The agent writes the ANSWER line itself, so the answer contract can no longer be the reason a task fails.
5. Before a program runs, slips a small model makes over and over are tidied mechanically (a unit written after a
   number, `x = 204.0 'ft'`; a money string, `'$21,500'`), so a retry is not spent on them.
6. Markdown tables in the prompt are parsed by the agent and handed to the program as `TABLES` (lists of row dicts,
   numbers already numbers), so a 20-cell grid is never retyped — transcription was a main source of wrong answers.
   A few textbook helpers (CPM pass, present value; see toolkit.py) are preloaded, and choice answers are snapped to
   the quoted options the prompt offers ("Option A" -> "A").
7. When the programs split on a field with no majority, more are sampled (up to `max_samples`); when no program runs
   at all, the model is asked for the answer directly rather than leaving the line empty.

Text only: image tasks go to `local:<model>+images`.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

from . import knowledge, toolkit
from .task import Task

# The type may carry detail after its name — "delivery_date" (string YYYY-MM-DD), "ids" (array of strings).
KEYS_RE = re.compile(r'"([A-Za-z_][\w]*)"\s*\((number|string|integer|text|boolean|date|list|array|object)\b[^)]*\)')

SYSTEM = """You are a construction engineer and estimator who solves problems by writing Python.
Write ONE Python program that solves the task:
- First assign every quantity given in the task to a clearly named variable, with its unit in a comment.
- Convert units explicitly (in→ft /12, sq ft→sq yd /9, cu ft→cu yd /27, min→h /60, %→fraction /100).
- Compute each answer in its own step. Follow the task's stated conventions and rounding rules exactly; do not round
  intermediate values unless the task says to.
- For yes/no or choice answers, compute the condition and produce exactly the words the task asks for.
- Numbers are plain Python numbers: no units, $, commas or % inside them (units go in comments: x = 204.0  # ft).
- Write tables from the task as lists of dicts with numeric values, and loop over them rather than retyping values.
- End with: print(json.dumps(answer)) where answer is a dict with exactly the answer keys.
Only the modules math, json, statistics, fractions, itertools and datetime are available. No input(), files or network.
Reply with the program in one ```python block and nothing else."""

ALLOWED_IMPORTS = {"math", "json", "statistics", "fractions", "itertools", "datetime", "decimal", "functools"}
FORBIDDEN = re.compile(r"\b(open|exec|eval|compile|__import__|globals|locals|getattr|setattr|input|breakpoint)\s*\(|"
                       r"\b(os|sys|subprocess|socket|shutil|pathlib|importlib|ctypes|builtins)\b\s*\.")

# Runs the model's program with a trimmed builtins table and an import hook that allows only ALLOWED_IMPORTS.
RUNNER = r"""
import builtins, sys, json
_real_import = builtins.__import__
# The program's own import lines are allow-listed before it runs (run_program); at run time only the modules that
# reach outside the process are refused, so the stdlib's internal imports (_io, _decimal, …) still work.
_deny = {'os', 'subprocess', 'socket', 'shutil', 'pathlib', 'ctypes', 'importlib', 'multiprocessing', 'urllib',
         'http', 'ftplib', 'smtplib', 'asyncio', 'signal', 'pty', 'posix', 'nt', 'io'}
def _imp(name, globals=None, *a, **k):
    if name.split('.')[0] in _deny and (globals or {}).get('__name__') == '__main__':
        raise ImportError('module not available: ' + name)
    return _real_import(name, globals, *a, **k)
builtins.__import__ = _imp
for n in ('open', 'input', 'breakpoint', 'exit', 'quit'):
    builtins.__dict__.pop(n, None)
job = json.loads(sys.stdin.read())
g = {'__name__': '__main__', 'TABLES': job['tables']}
if job['toolkit']:
    exec(compile(job['toolkit'], 'toolkit.py', 'exec'), g)
exec(compile(job['code'], 'program.py', 'exec'), g)
"""

TOOLKIT_SRC = open(os.path.join(os.path.dirname(__file__), "toolkit.py"), encoding="utf-8").read()


def _cell(v: str) -> Any:
    """A table cell as a number when it spells one ('$21,500' -> 21500, '12%' -> 12, '(3,000)' -> -3000)."""
    t = v.strip()
    neg = t.startswith("(") and t.endswith(")")
    n = t.strip("()").replace("$", "").replace(",", "").replace("%", "").strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", n):
        x = float(n)
        x = -x if neg else x
        return int(x) if x.is_integer() and "." not in n else x
    return t


def parse_tables(prompt: str) -> list[list[dict]]:
    """Every markdown table in the prompt -> a list of row dicts keyed by the header cells."""
    tables, lines, i = [], prompt.splitlines(), 0
    while i < len(lines) - 1:
        head, sep = lines[i].strip(), lines[i + 1].strip()
        if head.startswith("|") and re.fullmatch(r"\|?(\s*:?-{2,}:?\s*\|)+\s*:?-*:?\s*\|?", sep):
            cols = [c.strip() for c in head.strip("|").split("|")]
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                rows.append({c: _cell(v) for c, v in zip(cols, cells)})
                j += 1
            tables.append(rows)
            i = j
        else:
            i += 1
    return tables


def describe_tables(tables: list[list[dict]]) -> str:
    if not tables:
        return ""
    out = ["The task's tables are already loaded as TABLES (do not retype their values):"]
    for n, rows in enumerate(tables):
        cols = list(rows[0]) if rows else []
        out.append(f"- TABLES[{n}]: {len(rows)} rows, each a dict with keys {cols}; first row: "
                   f"{json.dumps(rows[0], ensure_ascii=False) if rows else '{}'}")
    out.append("Text cells stay strings (e.g. predecessors 'B, D'); money and percent cells are plain numbers.")
    return "\n".join(out)


def options_in(prompt: str, keys: list[tuple[str, str]]) -> list[str]:
    """Short quoted words the prompt offers as answers ("A" or "B", "import" or "export"), not the key names."""
    names = {k for k, _ in keys}
    return [o for o in dict.fromkeys(re.findall(r'"([^"\n]{1,24})"', prompt)) if o not in names]


def snap(value: Any, options: list[str]) -> Any:
    """A string answer -> the one offered option it names, case and padding aside; unchanged otherwise."""
    if not isinstance(value, str) or not options:
        return value
    v = value.strip().casefold()
    for o in options:
        if v == o.casefold():
            return o
    hits = [o for o in options if re.search(r"(?<!\w)" + re.escape(o.casefold()) + r"(?!\w)", v)]
    return hits[0] if len(hits) == 1 else value


HINTS = [
    ("NameError", "Define every variable before using it, spelled exactly the same."),
    ("subscriptable", "A number is being indexed like a list — check which variables are lists of rows."),
    ("string indices", "A string is being indexed like a dict — rows of TABLES are dicts: row['Column']."),
    ("KeyError", "That key does not exist; use the exact column names listed for TABLES."),
    ("could not convert", "A string with $, commas or % was converted; strip them, or use the number directly."),
    ("SyntaxError", "Fix the syntax; units go in comments, never after a number."),
    ("is not iterable", "A single number is being looped over — loop over a list instead."),
    ("ZeroDivisionError", "A divisor is zero — check that every input was read from the task."),
]


def hint(err: str) -> str:
    return next((h for k, h in HINTS if k in err), "")


def sanity(result: dict, keys: list[tuple[str, str]]) -> list[str]:
    """Answers that cannot be right whatever the task: a fraction where a whole number is asked for, a negative
    count, a number that is not finite. Each is sent back once; a program that still gives it is accepted."""
    out = []
    for k, kind in keys:
        v = result.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        if not math.isfinite(v):
            out.append(f'"{k}" is not a finite number.')
        elif kind == "integer" and abs(v - round(v)) > 1e-6:
            out.append(f'"{k}" must be a whole number but is {v:g} — apply the rounding the task states '
                       "(math.ceil for quantities to buy or units needed, math.floor for whole units that fit).")
        elif kind == "integer" and v < 0:
            out.append(f'"{k}" is a count but came out negative ({v:g}).')
    return out


def answer_keys(prompt: str) -> list[tuple[str, str]]:
    """[(key, type)] from the prompt's 'Answer keys:' line (or any "key" (type) list in the prompt)."""
    tail = prompt[prompt.rfind("Answer keys"):] if "Answer keys" in prompt else prompt
    seen, out = set(), []
    for k, t in KEYS_RE.findall(tail):
        if k not in seen:
            seen.add(k); out.append((k, t.split()[0].lower()))
    return out


def extract_code(reply: str) -> str:
    m = re.findall(r"```(?:python|py)?\s*\n(.*?)```", reply, re.S)
    if m:
        return max(m, key=len)
    return reply.strip()


UNIT_AFTER_NUMBER = re.compile(r"^(\s*[A-Za-z_]\w*\s*=\s*-?\d[\d_]*(?:\.\d+)?)\s+(?:'[^'\n]*'|\"[^\"\n]*\"|(?!(?:if|else|and|or|for|in|not|is|lambda)\b)[A-Za-z][\w/^ .-]*?)\s*(#.*)?$", re.M)
MONEY_STRING = re.compile(r"""(?<![\w\]])(['"])\$?(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\$\d+(?:\.\d+)?|\$-?\d+(?:\.\d+)?)\1(?!\s*[.\[])""")


def tidy(code: str) -> str:
    """Mechanical fixes for slips small models repeat: `x = 204.0 'ft'` / `x = 204 ft` -> `x = 204.0  # ft`, and a
    money or thousands-separated string literal ('$21,500', "1,250.5") -> the number it spells. Nothing else changes."""
    def unit(m: re.Match) -> str:
        tail = m.group(0)[len(m.group(1)):].strip()
        return m.group(1) + "  # " + tail.lstrip("#").strip()
    code = UNIT_AFTER_NUMBER.sub(unit, code)
    return MONEY_STRING.sub(lambda m: m.group(2).replace("$", "").replace(",", ""), code)


def run_program(code: str, timeout: int = 10, tables: list | None = None,
                toolkit: bool = True) -> tuple[dict | None, str]:
    """Runs the program (with TABLES and the toolkit preloaded); returns (the printed answer dict, or None; the error)."""
    code = tidy(code)
    if FORBIDDEN.search(code):
        return None, "The program uses something that is not available (files, os, sys, eval/exec, input)."
    for mod in re.findall(r"^\s*(?:from|import)\s+([A-Za-z_][\w]*)", code, re.M):
        if mod not in ALLOWED_IMPORTS:
            return None, f"Module '{mod}' is not available; use only {', '.join(sorted(ALLOWED_IMPORTS))}."
    if "import json" not in code:
        code = "import json\n" + code
    if "import math" not in code:
        code = "import math\n" + code
    with tempfile.TemporaryDirectory() as tmp:
        try:
            p = subprocess.run([sys.executable, "-I", "-S", "-c", RUNNER, "-", json.dumps(sorted(ALLOWED_IMPORTS))],
                               input=json.dumps({"code": code, "tables": tables or [],
                                                 "toolkit": TOOLKIT_SRC if toolkit else ""}),
                               capture_output=True, text=True, timeout=timeout, cwd=tmp,
                               env={"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0"})
        except subprocess.TimeoutExpired:
            return None, f"The program ran longer than {timeout} s."
    if p.returncode != 0:
        err = (p.stderr or "").strip().splitlines()
        return None, "\n".join(err[-4:]) or f"exit {p.returncode}"
    for line in reversed((p.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                v = json.loads(line)
                if isinstance(v, dict):
                    return v, ""
            except json.JSONDecodeError:
                continue
    return None, "The program did not print a JSON object on its last line (use print(json.dumps(answer)))."


def coerce(value: Any, kind: str) -> Any:
    if kind in ("number", "integer"):
        if isinstance(value, bool):
            return None
        if isinstance(value, str):
            try:
                value = float(value.replace(",", "").replace("$", "").strip().rstrip("%"))
            except ValueError:
                return None
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        if kind == "integer" and abs(value - round(value)) < 1e-6:
            return int(round(value))
        return value
    if kind in ("list", "array"):
        if isinstance(value, (tuple, set)):
            return sorted(value, key=str) if isinstance(value, set) else list(value)
        if isinstance(value, str):
            return [p.strip() for p in value.split(",") if p.strip()]
        return value if isinstance(value, list) else None
    if kind in ("string", "text"):
        if isinstance(value, bool):
            return "yes" if value else "no"
        return value if isinstance(value, str) else (json.dumps(value) if value is not None else None)
    return value


def vote(candidates: list[dict], keys: list[tuple[str, str]], support: dict | None = None) -> dict:
    """Per field, the value most programs agree on (numbers agree within 0.1%). Ties go to the earliest program.
    `support`, when given, is filled with how many programs back each chosen value."""
    out = {}
    for k, kind in keys:
        vals = [coerce(c.get(k), kind) for c in candidates if k in c]
        vals = [v for v in vals if v is not None]
        if not vals:
            continue
        if kind in ("number", "integer"):
            groups: list[list[float]] = []
            for v in vals:
                for g in groups:
                    if abs(g[0] - v) <= max(1e-9, 1e-3 * max(abs(g[0]), abs(v))):
                        g.append(v); break
                else:
                    groups.append([v])
            best_group = max(groups, key=len)
            out[k] = best_group[0]
            if support is not None:
                support[k] = len(best_group)
        else:
            # Lists that hold the same items in another order agree (most list answers are sets of IDs).
            def norm(v):
                return json.dumps(sorted(map(str, v)) if isinstance(v, list) else v, sort_keys=True)
            counts = Counter(norm(v) for v in vals)
            best, n = max(counts.items(), key=lambda kv: kv[1])
            out[k] = next(v for v in vals if norm(v) == best)
            if support is not None:
                support[k] = n
    return out


class Agent:
    """Program-of-thought with feedback and voting over a local OpenAI-compatible model."""

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:1234/v1", samples: int = 3,
                 retries: int = 2, max_tokens: int = 2048, timeout: int = 600, max_samples: int = 5,
                 tables: bool = True, toolkit: bool = True, knowledge: bool = True, checks: bool = True):
        self.model, self.base_url = model, base_url.rstrip("/")
        self.use_tables, self.use_toolkit = tables, toolkit
        self.use_knowledge, self.use_checks = knowledge, checks
        self.samples, self.retries, self.max_tokens, self.timeout = samples, retries, max_tokens, timeout
        self.max_samples = max(samples, max_samples)
        self.name = f"ci:{model}"
        self.supports_images = False
        self.tokens_in = self.tokens_out = 0

    def _chat(self, messages: list[dict], temperature: float) -> str:
        body = {"model": self.model, "max_tokens": self.max_tokens, "temperature": temperature, "messages": messages}
        req = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": "Bearer " + os.environ["LOCAL_API_KEY"]}
                                                 if os.environ.get("LOCAL_API_KEY") else {})})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out = json.load(r)
                u = out.get("usage") or {}
                self.tokens_in += u.get("prompt_tokens") or 0
                self.tokens_out += u.get("completion_tokens") or 0
                return out["choices"][0]["message"].get("content") or ""
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and attempt < 2:
                    time.sleep(3 * 2 ** attempt); continue
                raise
        raise RuntimeError("retries exhausted")

    def _one_program(self, prompt: str, keys: list[tuple[str, str]], temperature: float, log: list,
                     tables: list | None = None) -> dict | None:
        """One program, fixed up to `retries` times from its own error. A dict missing some keys is kept as a
        fallback in case no fix completes it."""
        key_line = ", ".join(f'"{k}" ({t}' + (f", {u}" if (u := knowledge.unit_of(k, t)) else "") + ")" for k, t in keys)
        extra = [knowledge.reference(prompt) if self.use_knowledge else "",
                 describe_tables(tables or []), toolkit.HELP if self.use_toolkit else "",
                 f"The answer dict must have exactly these keys: {key_line}." if keys else ""]
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt + "".join("\n\n" + e for e in extra if e)}]
        best: dict | None = None
        for attempt in range(self.retries + 1):
            reply = self._chat(messages, temperature if attempt == 0 else max(temperature, 0.2))
            result, err = run_program(extract_code(reply), tables=tables, toolkit=self.use_toolkit)
            if result is not None and keys:
                missing = [k for k, _ in keys if k not in result]
                if missing:
                    err = f"The printed dict is missing keys: {', '.join(missing)}."
                    if best is None or len(result) > len(best):
                        best = result
                    result = None
            issues = sanity(result, keys) if result is not None and self.use_checks else []
            log.append({"t": temperature, "attempt": attempt, "error": err or None, "result": result,
                        **({"issues": issues} if issues else {})})
            if result is not None and (not issues or attempt == self.retries):
                return result
            if result is not None:
                # It ran, but an answer is implausible: keep it, and ask once more with the reason.
                best = result
                feedback = (f"The program ran and printed {json.dumps(result)}, but: {' '.join(issues)} Re-read the "
                            "task, fix the program and reply with the whole corrected program.")
            else:
                feedback = (f"Running that program failed:\n{err}\n{hint(err)}\n"
                            "Fix it and reply with the whole corrected program.")
            messages += [{"role": "assistant", "content": reply}, {"role": "user", "content": feedback}]
        return best

    def _direct(self, prompt: str, keys: list[tuple[str, str]]) -> dict:
        """Last resort when no program ran: ask for the answer itself and keep the answer-key fields of the last JSON
        object in the reply."""
        from .providers import SYSTEM as PLAIN
        reply = self._chat([{"role": "system", "content": PLAIN}, {"role": "user", "content": prompt}], 0.0)
        for m in reversed(list(re.finditer(r"\{[^{}]*\}", reply))):
            try:
                d = json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
            if isinstance(d, dict):
                return {k: v for k, v in d.items() if not keys or k in dict(keys)}
        return {}

    def answer(self, task: Task):
        from .providers import Response
        t0 = time.time()
        keys = answer_keys(task.prompt)
        tables = parse_tables(task.prompt) if self.use_tables else []
        log: list = []
        note = ""
        try:
            temps = [0.0] + [0.6] * (self.samples - 1)
            candidates = [c for c in (self._one_program(task.prompt, keys, t, log, tables) for t in temps) if c]
            # A split with no majority on some field: sample more programs (up to max_samples) to break it.
            while keys and candidates and len(temps) < self.max_samples:
                support: dict = {}
                vote(candidates, keys, support)
                if all(support.get(k, 0) >= 2 for k, _ in keys):
                    break
                temps.append(0.8)
                c = self._one_program(task.prompt, keys, 0.8, log, tables)
                if c:
                    candidates.append(c)
            final = vote(candidates, keys) if keys else (candidates[0] if candidates else {})
            if not candidates:
                final, note = self._direct(task.prompt, keys), " Answered directly."
        except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
            return Response(text="", ok=False, error=f"connection: {e}", seconds=time.time() - t0)
        options = options_in(task.prompt, keys)
        final = {k: snap(v, options) if kind in ("string", "text") else v for k, v in final.items()
                 for kind in [dict(keys).get(k, "")]}
        text = f"{len(candidates)} of {len(temps)} programs ran.{note}\nANSWER: {json.dumps(final)}"
        return Response(text=text, input_tokens=self.tokens_in, output_tokens=self.tokens_out,
                        seconds=time.time() - t0, extra={"programs": log[-12:]})
