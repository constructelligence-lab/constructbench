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

Text only: image tasks go to `local:<model>+images`.
"""
from __future__ import annotations

import json
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

from .task import Task

KEYS_RE = re.compile(r'"([A-Za-z_][\w]*)"\s*\((number|string|integer|text|boolean|list[^)]*|array[^)]*|object[^)]*)\)')

SYSTEM = """You are a construction engineer and estimator who solves problems by writing Python.
Write ONE Python program that solves the task:
- First assign every quantity given in the task to a clearly named variable, with its unit in a comment.
- Convert units explicitly (in→ft /12, sq ft→sq yd /9, cu ft→cu yd /27, min→h /60, %→fraction /100).
- Compute each answer in its own step. Follow the task's stated conventions and rounding rules exactly; do not round
  intermediate values unless the task says to.
- For yes/no or choice answers, compute the condition and produce exactly the words the task asks for.
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
src = sys.stdin.read()
exec(compile(src, 'program.py', 'exec'), {'__name__': '__main__'})
"""


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


def run_program(code: str, timeout: int = 10) -> tuple[dict | None, str]:
    """Runs the program; returns (the printed answer dict, or None; the error text)."""
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
                               input=code, capture_output=True, text=True, timeout=timeout, cwd=tmp,
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
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            s = value.replace(",", "").replace("$", "").strip().rstrip("%")
            try:
                return float(s)
            except ValueError:
                return None
        return None
    if kind in ("string", "text"):
        if isinstance(value, bool):
            return "yes" if value else "no"
        return value if isinstance(value, str) else (json.dumps(value) if value is not None else None)
    return value


def vote(candidates: list[dict], keys: list[tuple[str, str]]) -> dict:
    """Per field, the value most programs agree on (numbers agree within 0.1%). Ties go to the earliest program."""
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
            out[k] = max(groups, key=len)[0]
        else:
            counts = Counter(json.dumps(v, sort_keys=True) for v in vals)
            best = max(counts.items(), key=lambda kv: kv[1])[0]
            out[k] = json.loads(best)
    return out


class Agent:
    """Program-of-thought with feedback and voting over a local OpenAI-compatible model."""

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:1234/v1", samples: int = 3,
                 retries: int = 2, max_tokens: int = 2048, timeout: int = 600):
        self.model, self.base_url = model, base_url.rstrip("/")
        self.samples, self.retries, self.max_tokens, self.timeout = samples, retries, max_tokens, timeout
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

    def _one_program(self, prompt: str, keys: list[tuple[str, str]], temperature: float, log: list) -> dict | None:
        """One program, fixed up to `retries` times from its own error. A dict missing some keys is kept as a
        fallback in case no fix completes it."""
        key_line = ", ".join(f'"{k}" ({t})' for k, t in keys)
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt + (f"\n\nThe answer dict must have exactly these keys: {key_line}." if keys else "")}]
        best: dict | None = None
        for attempt in range(self.retries + 1):
            reply = self._chat(messages, temperature if attempt == 0 else max(temperature, 0.2))
            result, err = run_program(extract_code(reply))
            if result is not None and keys:
                missing = [k for k, _ in keys if k not in result]
                if missing:
                    err = f"The printed dict is missing keys: {', '.join(missing)}."
                    if best is None or len(result) > len(best):
                        best = result
                    result = None
            log.append({"t": temperature, "attempt": attempt, "error": err or None, "result": result})
            if result is not None:
                return result
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": f"Running that program failed:\n{err}\nFix it and reply with the whole corrected program."}]
        return best

    def answer(self, task: Task):
        from .providers import Response
        t0 = time.time()
        keys = answer_keys(task.prompt)
        log: list = []
        try:
            temps = [0.0] + [0.6] * (self.samples - 1)
            candidates = [c for c in (self._one_program(task.prompt, keys, t, log) for t in temps) if c]
        except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
            return Response(text="", ok=False, error=f"connection: {e}", seconds=time.time() - t0)
        final = vote(candidates, keys) if keys else (candidates[0] if candidates else {})
        text = f"{len(candidates)} of {len(temps)} programs ran.\nANSWER: {json.dumps(final)}"
        return Response(text=text, input_tokens=self.tokens_in, output_tokens=self.tokens_out,
                        seconds=time.time() - t0, extra={"programs": log[-12:]})
