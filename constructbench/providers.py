"""Who answers the tasks.

  anthropic:<model>[+code][+submit]
                      Claude via the official `anthropic` SDK (pip install anthropic; credentials from the
                      environment or `ant auth login`). Default model: claude-opus-5-5.
                      +code   gives Claude a run_python tool: the agent's sandbox, with the task's tables/texts/lists
                              and the toolkit (cpm, npv, irr, round_half_up, …) preloaded — numbers get computed, not
                              worked in its head.
                      +submit gives Claude a submit_answer tool whose strict schema is built from the prompt's
                              "Answer keys" line (never the grader), so the answer can't fail on format.
                      Plain anthropic:<model> is the no-harness baseline; run both to measure the harness.
  local:<model>[@<base url>][+images][+code][+submit]
  api:<model>@<base url>[+code][+submit]
                      Any model behind an OpenAI-compatible /chat/completions endpoint — open weights on LM Studio
                      (default http://127.0.0.1:1234/v1), Ollama (http://127.0.0.1:11434/v1), llama.cpp, vLLM, or a
                      hosted API (api:deepseek-chat@https://api.deepseek.com/v1). The key comes from LOCAL_API_KEY or
                      the host's own variable (DEEPSEEK_API_KEY, OPENROUTER_API_KEY, … — KEY_ENV). +images sends image
                      tasks to a vision model; +code/+submit are the same harness as Claude's, via function calling.
                      This is also how the Constructelligence assistant's own open model is served ("our model").
  ci:<model>[@<base url>]
                      The Constructelligence small-model agent (agent.py): the same local model, writing a Python program
                      per task that the agent runs, fixes from its own errors and votes over — the answer shape taken from
                      the prompt's "Answer keys" line, never from the grader. Text tasks only.
  command:<shell cmd> Any other model or local runtime: the prompt goes to the command's stdin and its stdout is
                      the response (e.g. `command:ollama run llama3.1`). Images are not passed; visual tasks are
                      skipped for text-only providers.
  oracle              Answers every task correctly — checks the harness end to end (must score 100%).
  blank               Never answers — the floor (must score 0%).
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from .task import Task

SYSTEM = ("You are being evaluated on construction industry tasks. Work the problem however you like, then end your "
          "reply with exactly one line of the form\nANSWER: {json}\nwhere the JSON object has exactly the keys the "
          "task names. Use plain numbers (no $ or commas) and do not round intermediate steps.")


@dataclass
class Response:
    text: str
    ok: bool = True
    error: str | None = None
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    seconds: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


class Provider:
    name = "provider"
    supports_images = False

    def answer(self, task: Task) -> Response:  # pragma: no cover - interface
        raise NotImplementedError


class Oracle(Provider):
    name = "oracle"
    supports_images = True

    def answer(self, task: Task) -> Response:
        return Response(text="Reference answer.\nANSWER: " + json.dumps(task.answer))


class Blank(Provider):
    name = "blank"
    supports_images = True

    def answer(self, task: Task) -> Response:
        return Response(text="I don't know.")


class Command(Provider):
    supports_images = False

    def __init__(self, cmd: str, timeout: int = 600):
        self.cmd, self.timeout = cmd, timeout
        self.name = "command:" + cmd

    def answer(self, task: Task) -> Response:
        t0 = time.time()
        try:
            p = subprocess.run(shlex.split(self.cmd), input=SYSTEM + "\n\n" + task.prompt, capture_output=True,
                               text=True, timeout=self.timeout)
            return Response(text=p.stdout, ok=p.returncode == 0, error=p.stderr[-500:] if p.returncode else None,
                            seconds=time.time() - t0)
        except subprocess.TimeoutExpired:
            return Response(text="", ok=False, error="timeout", seconds=time.time() - t0)


# The harness's only words to the model besides SYSTEM and the tool descriptions (recorded in every run manifest).
CODE_NOTE = ("Do every calculation with run_python — quantities, unit conversions, rounding, dates, schedules — "
             "rather than working numbers out in your head. Check each result makes sense.")
SUBMIT_NOTE = "When you are done, call submit_answer with the final values instead of writing an ANSWER line."
RUN_PYTHON_DESC = ("Runs a Python program in a fresh sandbox and returns its stdout (or the error). Nothing persists "
                   "between calls. Modules: {modules}; no files, network or input(). Print what you need to see.\n"
                   "{toolkit}{loaded}")
SUBMIT_DESC = "Submit the final answer. Call it exactly once, when you are done."
LAST_TURN_NOTE = "Last turn: submit your final answer now."


class Toolbox:
    """The +code / +submit harness for one task, shared by every API so each model gets the same tools and words.

    run_python is the ci: agent's sandbox with the task's tables/texts/lists and the toolkit preloaded; submit_answer's
    schema comes from the prompt's own "Answer keys" line (never the grader). Where the API cannot enforce the schema
    (OpenAI-compatible servers), a submission with missing or mistyped keys is sent back once to be fixed.
    """

    def __init__(self, task: Task, code: bool, submit: bool):
        from . import agent
        self._agent = agent
        self.keys = agent.answer_keys(task.prompt)
        self.code, self.submit = code, submit and bool(self.keys)  # no parsable keys -> the ANSWER line instead
        self.inputs = agent.prompt_inputs(task.prompt)
        self.submitted: dict | None = None
        self.runs = self.rejected = 0
        self.tools: list[dict[str, Any]] = []
        notes = [SYSTEM]
        if self.code:
            loaded = agent.describe_inputs(self.inputs)
            self.tools.append({
                "name": "run_python",
                "description": RUN_PYTHON_DESC.format(modules=", ".join(sorted(agent.ALLOWED_IMPORTS)),
                                                      toolkit=toolkit_help(), loaded=("\n" + loaded if loaded else "")),
                "schema": {"type": "object", "properties": {"code": {"type": "string"}},
                           "required": ["code"], "additionalProperties": False},
            })
            notes.append(CODE_NOTE)
        if self.submit:
            self.tools.append({"name": "submit_answer",
                               "description": SUBMIT_DESC,
                               "schema": answer_schema(self.keys)})
            notes.append(SUBMIT_NOTE)
        self.system = "\n\n".join(notes)

    def call(self, name: str, args: Any) -> tuple[str, bool]:
        """Runs one tool call -> (result text, is_error). A valid submit_answer sets self.submitted."""
        if not isinstance(args, dict):
            return "Arguments must be a JSON object.", True
        if name == "submit_answer" and self.submit:
            problems = [f'"{k}" is missing' for k, _ in self.keys if k not in args]
            problems += [f'"{k}" should be {kind}' for k, kind in self.keys
                         if k in args and self._agent.coerce(args[k], kind) is None]
            problems += [f'"{k}" is not an answer key' for k in args if k not in dict(self.keys)]
            if problems and self.rejected == 0:
                self.rejected += 1
                return "Not recorded: " + "; ".join(problems) + ". Submit again with exactly the answer keys.", True
            self.submitted = {k: args[k] for k, _ in self.keys if k in args}
            return "Recorded.", False
        if name == "run_python" and self.code:
            self.runs += 1
            ok, out, err = self._agent.execute(str(args.get("code", "")), timeout=30, inputs=self.inputs)
            return (out[-8000:] + ("\n" + err if err else "")).strip() or "(no output — print what you need)", not ok
        return f"Unknown tool {name!r}.", True

    def finish(self, text: str) -> str:
        return text.rstrip() + "\nANSWER: " + json.dumps(self.submitted) if self.submitted is not None else text

    def extra(self, turns: int) -> dict[str, Any]:
        return {"turns": turns, "code_runs": self.runs, "submitted": self.submitted is not None,
                "rejected_submits": self.rejected}


# USD per million tokens: (input, output, cache read). Cache writes (5-minute) bill at 1.25x input. From the
# Anthropic price list as of 2026-10; a model not listed records no cost and a --budget cannot protect it.
PRICES = {"claude-opus-5-5": (4.0, 20.0, 0.20), "claude-opus-5": (5.0, 25.0, 0.50),
          "claude-sonnet-5-5": (2.0, 10.0, 0.20), "claude-sonnet-5": (2.0, 10.0, 0.20),
          "claude-haiku-5-5": (0.10, 0.50, 0.01), "claude-fable-5-1": (10.0, 50.0, 0.25)}


def claude_cost(model: str, usage: Any) -> float | None:
    p = PRICES.get(model)
    if p is None:
        return None
    cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cr = getattr(usage, "cache_read_input_tokens", 0) or 0
    return (usage.input_tokens * p[0] + cw * p[0] * 1.25 + cr * p[2] + usage.output_tokens * p[1]) / 1e6


class Claude(Provider):
    """Claude through the official SDK. Adaptive thinking; effort is a run setting so it is recorded with results.

    No server-side refusal fallback on purpose: a fallback would answer with a different model and the score would
    no longer measure the model named in the run. A refusal is recorded as a refusal.

    With `code` and/or `submit` it runs a manual tool loop (Toolbox). Tool choice stays "auto" — current models
    reject forced tool use — so the system prompt asks for the tools instead. A key that is not scoped to a workspace
    needs ANTHROPIC_WORKSPACE_ID (sent as the anthropic-workspace-id header).
    """
    supports_images = True
    max_turns = 12
    max_task_cost: float | None = None   # USD: a tool loop that passes it stops and keeps what it has

    def __init__(self, model: str = "claude-opus-5-5", effort: str = "high", max_tokens: int = 16000,
                 code: bool = False, submit: bool = False):
        import anthropic  # imported here so the harness itself needs nothing installed
        self._anthropic = anthropic
        ws = os.environ.get("ANTHROPIC_WORKSPACE_ID")
        self.client = anthropic.Anthropic(max_retries=4,
                                          **({"default_headers": {"anthropic-workspace-id": ws}} if ws else {}))
        self.model, self.effort, self.max_tokens = model, effort, max_tokens
        self.code, self.submit = code, submit
        self.name = f"anthropic:{model}{'+code' if code else ''}{'+submit' if submit else ''}@{effort}"

    def _content(self, task: Task) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": a["media_type"], "data": a["data"]}}
            for a in task.attachments
        ]
        content.append({"type": "text", "text": task.prompt})
        return content

    def _create(self, **kw):
        a = self._anthropic
        try:
            return self.client.messages.create(model=self.model, max_tokens=self.max_tokens,
                                               thinking={"type": "adaptive"},
                                               output_config={"effort": self.effort}, **kw), None
        except a.RateLimitError as e:
            return None, f"rate limited: {e.message}"
        except a.APIStatusError as e:
            return None, f"HTTP {e.status_code}: {e.message}"
        except a.APIConnectionError as e:
            return None, f"connection: {e}"

    def answer(self, task: Task) -> Response:
        if self.code or self.submit:
            return self._tool_loop(task)
        t0 = time.time()
        msg, err = self._create(system=SYSTEM, messages=[{"role": "user", "content": self._content(task)}])
        if err:
            return Response(text="", ok=False, error=err, seconds=time.time() - t0)
        text = "".join(b.text for b in msg.content if b.type == "text")
        cost = claude_cost(self.model, msg.usage)
        return Response(text=text, stop_reason=msg.stop_reason, input_tokens=msg.usage.input_tokens,
                        output_tokens=msg.usage.output_tokens, seconds=time.time() - t0,
                        ok=msg.stop_reason != "refusal", error="refusal" if msg.stop_reason == "refusal" else None,
                        extra={} if cost is None else {"cost_usd": cost})

    def _tool_loop(self, task: Task) -> Response:
        box = Toolbox(task, self.code, self.submit)
        tools = [{"name": t["name"], "description": t["description"], "input_schema": t["schema"], "strict": True}
                 for t in box.tools]
        sys_blocks = [{"type": "text", "text": box.system}]
        messages: list[dict[str, Any]] = [{"role": "user", "content": self._content(task)}]
        t0, tin, tout, turns, text, stop, cost = time.time(), 0, 0, 0, "", None, 0.0
        while turns < self.max_turns:
            turns += 1
            msg, err = self._create(system=sys_blocks, tools=tools, tool_choice={"type": "auto"},
                                    cache_control={"type": "ephemeral"}, messages=messages)
            if err:
                return Response(text=text, ok=False, error=err, seconds=time.time() - t0, input_tokens=tin,
                                output_tokens=tout, extra={**box.extra(turns), "cost_usd": cost})
            c = claude_cost(self.model, msg.usage)
            cost = None if c is None or cost is None else cost + c
            tin += msg.usage.input_tokens + (msg.usage.cache_read_input_tokens or 0) + \
                (msg.usage.cache_creation_input_tokens or 0)
            tout += msg.usage.output_tokens
            stop = msg.stop_reason
            text += "".join(b.text for b in msg.content if b.type == "text")
            calls = [b for b in msg.content if b.type == "tool_use"]
            if stop == "refusal" or stop != "tool_use" or not calls:
                break
            messages.append({"role": "assistant", "content": msg.content})  # whole content: keeps thinking blocks
            results = []
            for c in calls:
                body, is_err = box.call(c.name, c.input)
                results.append({"type": "tool_result", "tool_use_id": c.id, "content": body, "is_error": is_err})
            if box.submitted is not None:
                break
            messages.append({"role": "user", "content": results})
            if self.max_task_cost is not None and cost is not None and cost >= self.max_task_cost:
                stop = "task_budget"
                break
            if turns == self.max_turns - 1 or (self.max_task_cost is not None and cost is not None
                                               and cost >= 0.6 * self.max_task_cost):
                messages[-1]["content"].append({"type": "text", "text": LAST_TURN_NOTE})
        return Response(text=box.finish(text), stop_reason=stop, input_tokens=tin, output_tokens=tout,
                        seconds=time.time() - t0, ok=stop != "refusal", error="refusal" if stop == "refusal" else None,
                        extra={**box.extra(turns), **({} if cost is None else {"cost_usd": cost})})


def toolkit_help() -> str:
    from . import toolkit
    return toolkit.HELP


def answer_schema(keys: list[tuple[str, str]]) -> dict[str, Any]:
    """A strict JSON schema for submit_answer from the prompt's own Answer keys line — types only, never values."""
    kinds = {"number": {"type": "number"}, "integer": {"type": "integer"}, "boolean": {"type": "boolean"},
             "list": {"type": "array", "items": {"type": "string"}},
             "array": {"type": "array", "items": {"type": "string"}}}
    props = {k: kinds.get(kind, {"type": "string"}) for k, kind in keys}
    return {"type": "object", "properties": props, "required": [k for k, _ in keys], "additionalProperties": False}


# Key env var by host, so one shell can hold keys for several OpenAI-compatible services. LOCAL_API_KEY wins.
KEY_ENV = {"api.deepseek.com": "DEEPSEEK_API_KEY", "openrouter.ai": "OPENROUTER_API_KEY",
           "api.openai.com": "OPENAI_API_KEY", "api.together.xyz": "TOGETHER_API_KEY",
           "api.groq.com": "GROQ_API_KEY", "api.fireworks.ai": "FIREWORKS_API_KEY",
           "generativelanguage.googleapis.com": "GEMINI_API_KEY", "api.mistral.ai": "MISTRAL_API_KEY"}


class Local(Provider):
    """Any model behind an OpenAI-compatible /chat/completions endpoint (stdlib HTTP, no SDK): open weights on
    LM Studio / Ollama / vLLM, or a hosted API (DeepSeek, OpenRouter, …). +code/+submit use function calling with the
    same Toolbox as Claude; servers can't all enforce schemas, so Toolbox checks submissions itself."""
    max_turns = 12

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:1234/v1", images: bool = False,
                 max_tokens: int = 4096, timeout: int = 900, code: bool = False, submit: bool = False):
        self.model, self.base_url, self.max_tokens, self.timeout = model, base_url.rstrip("/"), max_tokens, timeout
        self.supports_images = images
        self.code, self.submit = code, submit
        host = urllib.parse.urlparse(self.base_url).hostname or ""
        self.hosted = host not in ("127.0.0.1", "localhost", "0.0.0.0")
        env = KEY_ENV.get(host)
        self.key = os.environ.get("LOCAL_API_KEY") or (os.environ.get(env) if env else None)
        if self.hosted and not self.key:
            raise ValueError(f"no API key for {host}: set {env or 'LOCAL_API_KEY'}")
        flags = ("+code" if code else "") + ("+submit" if submit else "")
        self.name = f"{'api' if self.hosted else 'local'}:{model}{flags}"

    def _post(self, body: dict) -> tuple[dict | None, str | None]:
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        req = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(body).encode(), headers=headers)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.load(r), None
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                    time.sleep(min(60, 2 ** attempt * 3)); continue
                return None, f"HTTP {e.code}: {e.read()[:300]!r}"
            except (urllib.error.URLError, TimeoutError) as e:
                if self.hosted and attempt < 4:
                    time.sleep(min(60, 2 ** attempt * 3)); continue
                return None, f"connection: {e}"
        return None, "retries exhausted"

    def _user(self, task: Task) -> Any:
        if task.attachments and self.supports_images:
            return [{"type": "image_url", "image_url": {"url": f"data:{a['media_type']};base64,{a['data']}"}}
                    for a in task.attachments] + [{"type": "text", "text": task.prompt}]
        return task.prompt

    def answer(self, task: Task) -> Response:
        if self.code or self.submit:
            return self._tool_loop(task)
        t0 = time.time()
        out, err = self._post({"model": self.model, "max_tokens": self.max_tokens, "temperature": 0,
                               "messages": [{"role": "system", "content": SYSTEM},
                                            {"role": "user", "content": self._user(task)}]})
        if err:
            return Response(text="", ok=False, error=err, seconds=time.time() - t0)
        ch = out["choices"][0]
        usage = out.get("usage") or {}
        raw = _usage_totals({}, usage)
        cost = _usage_cost(raw)
        return Response(text=ch["message"].get("content") or "", stop_reason=ch.get("finish_reason"),
                        input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
                        seconds=time.time() - t0,
                        extra={"usage": raw, **({} if cost is None else {"cost_usd": cost})})

    def _tool_loop(self, task: Task) -> Response:
        box = Toolbox(task, self.code, self.submit)
        tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                   "parameters": t["schema"]}} for t in box.tools]
        messages: list[dict[str, Any]] = [{"role": "system", "content": box.system},
                                          {"role": "user", "content": self._user(task)}]
        t0, tin, tout, turns, text, stop, raw = time.time(), 0, 0, 0, "", None, {}
        while turns < self.max_turns:
            turns += 1
            out, err = self._post({"model": self.model, "max_tokens": self.max_tokens, "temperature": 0,
                                   "messages": messages, "tools": tools, "tool_choice": "auto"})
            if err:
                cost = _usage_cost(raw)
                return Response(text=text, ok=False, error=err, seconds=time.time() - t0, input_tokens=tin,
                                output_tokens=tout, extra={**box.extra(turns), "usage": raw,
                                                           **({} if cost is None else {"cost_usd": cost})})
            usage = out.get("usage") or {}
            raw = _usage_totals(raw, usage)
            tin += usage.get("prompt_tokens") or 0
            tout += usage.get("completion_tokens") or 0
            ch = out["choices"][0]
            msg, stop = ch["message"], ch.get("finish_reason")
            text += msg.get("content") or ""
            calls = msg.get("tool_calls") or []
            if not calls:
                break
            # echoed as returned: DeepSeek's thinking mode needs its reasoning_content back within a tool-call turn
            messages.append({k: v for k, v in msg.items() if v is not None})
            for c in calls:
                fn = c.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = None
                body, is_err = box.call(fn.get("name", ""), args) if args is not None else \
                    ("Arguments were not valid JSON.", True)
                messages.append({"role": "tool", "tool_call_id": c.get("id", ""),
                                 "content": ("ERROR: " if is_err else "") + body})
            if box.submitted is not None:
                break
            if turns == self.max_turns - 1:
                messages.append({"role": "user", "content": LAST_TURN_NOTE})
        cost = _usage_cost(raw)
        return Response(text=box.finish(text), stop_reason=stop, input_tokens=tin, output_tokens=tout,
                        seconds=time.time() - t0,
                        extra={**box.extra(turns), "usage": raw, **({} if cost is None else {"cost_usd": cost})})


def _usage_totals(acc: dict, usage: dict) -> dict:
    """Adds an OpenAI-compatible usage block into running totals, keeping every numeric field the server reports
    (DeepSeek: prompt_cache_hit_tokens / prompt_cache_miss_tokens; reasoning tokens under completion_tokens_details),
    so cost can be computed afterwards from the provider's price list instead of a guessed one."""
    out = dict(acc)
    for k, v in (usage or {}).items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = out.get(k, 0) + v
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, (int, float)) and not isinstance(v2, bool):
                    out[f"{k}.{k2}"] = out.get(f"{k}.{k2}", 0) + v2
    return out


def _usage_cost(raw: dict) -> float | None:
    """A server-reported cost for the task, when the API sends one — OpenRouter puts it in usage.cost, and
    _usage_totals sums it over the tool turns. Returns None when the server reports no cost."""
    c = raw.get("cost")
    return c if isinstance(c, (int, float)) and not isinstance(c, bool) else None


def _flags(rest: str, allowed: set[str]) -> tuple[str, set[str]]:
    head, *flags = rest.split("+")
    unknown = set(flags) - allowed
    if unknown:
        raise ValueError(f"unknown flag(s) {sorted(unknown)} — allowed: {', '.join('+' + f for f in sorted(allowed))}")
    return head, set(flags)


def make(spec: str, effort: str = "high", max_tokens: int | None = None) -> Provider:
    if spec == "oracle":
        return Oracle()
    if spec == "blank":
        return Blank()
    if spec.startswith(("local:", "api:")):
        rest, flags = _flags(spec.split(":", 1)[1], {"images", "code", "submit"})
        model, _, url = rest.partition("@")
        return Local(model, url or "http://127.0.0.1:1234/v1", images="images" in flags,
                     max_tokens=max_tokens or 4096, code="code" in flags, submit="submit" in flags)
    if spec.startswith("ci:"):
        from .agent import Agent
        model, _, url = spec[len("ci:"):].partition("@")
        return Agent(model, url or "http://127.0.0.1:1234/v1")
    if spec.startswith("command:"):
        return Command(spec[len("command:"):])
    if spec.startswith("anthropic:") or spec == "anthropic":
        model, flags = _flags(spec.split(":", 1)[1] if ":" in spec else "", {"code", "submit"})
        return Claude(model or "claude-opus-5-5", effort=effort, max_tokens=max_tokens or 16000,
                      code="code" in flags, submit="submit" in flags)
    raise ValueError(f"unknown provider {spec!r} — use anthropic:, local:, api:, ci:, command:, oracle or blank")
