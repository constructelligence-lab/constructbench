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
  local:<model>[@<base url>]
                      A model on an OpenAI-compatible local server — LM Studio (default http://127.0.0.1:1234/v1),
                      Ollama (http://127.0.0.1:11434/v1), llama.cpp, vLLM. This is how the Constructelligence
                      assistant's own open model is served, so this is the provider for "our model".
                      Add --images to send image tasks to a vision model.
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


class Claude(Provider):
    """Claude through the official SDK. Adaptive thinking; effort is a run setting so it is recorded with results.

    No server-side refusal fallback on purpose: a fallback would answer with a different model and the score would
    no longer measure the model named in the run. A refusal is recorded as a refusal.

    With `code` and/or `submit` it runs a manual tool loop (see the module docstring). Tool choice stays "auto" —
    current models reject forced tool use — so the system prompt asks for the tools instead.
    """
    supports_images = True
    max_turns = 12

    def __init__(self, model: str = "claude-opus-5-5", effort: str = "high", max_tokens: int = 16000,
                 code: bool = False, submit: bool = False):
        import anthropic  # imported here so the harness itself needs nothing installed
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=4)
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
        return Response(text=text, stop_reason=msg.stop_reason, input_tokens=msg.usage.input_tokens,
                        output_tokens=msg.usage.output_tokens, seconds=time.time() - t0,
                        ok=msg.stop_reason != "refusal", error="refusal" if msg.stop_reason == "refusal" else None)

    def _tool_loop(self, task: Task) -> Response:
        from . import agent
        keys = agent.answer_keys(task.prompt)
        submit = self.submit and bool(keys)  # no parsable keys -> fall back to the ANSWER line
        inputs = agent.prompt_inputs(task.prompt)
        tools, system = [], [SYSTEM]
        if self.code:
            loaded = agent.describe_inputs(inputs)
            tools.append({
                "name": "run_python",
                "description": ("Runs a Python program in a fresh sandbox and returns its stdout (or the error). "
                                "Nothing persists between calls. Modules: " + ", ".join(sorted(agent.ALLOWED_IMPORTS)) +
                                "; no files, network or input(). Print what you need to see.\n" + toolkit_help() +
                                ("\n" + loaded if loaded else "")),
                "input_schema": {"type": "object", "properties": {"code": {"type": "string"}},
                                 "required": ["code"], "additionalProperties": False},
                "strict": True,
            })
            system.append("Do every calculation with run_python — quantities, unit conversions, rounding, dates, "
                          "schedules — rather than working numbers out in your head. Check each result makes sense.")
        if submit:
            tools.append({
                "name": "submit_answer",
                "description": "Submit the final answer. Call it exactly once, when you are done.",
                "input_schema": answer_schema(keys),
                "strict": True,
            })
            system.append("When you are done, call submit_answer with the final values instead of writing an "
                          "ANSWER line.")
        sys_blocks = [{"type": "text", "text": "\n\n".join(system)}]
        messages: list[dict[str, Any]] = [{"role": "user", "content": self._content(task)}]
        t0, tin, tout, runs, turns = time.time(), 0, 0, 0, 0
        text, submitted, stop = "", None, None
        while turns < self.max_turns:
            turns += 1
            msg, err = self._create(system=sys_blocks, tools=tools, tool_choice={"type": "auto"},
                                    cache_control={"type": "ephemeral"}, messages=messages)
            if err:
                return Response(text=text, ok=False, error=err, seconds=time.time() - t0, input_tokens=tin,
                                output_tokens=tout, extra={"turns": turns, "code_runs": runs})
            tin += msg.usage.input_tokens + (msg.usage.cache_read_input_tokens or 0) + \
                (msg.usage.cache_creation_input_tokens or 0)
            tout += msg.usage.output_tokens
            stop = msg.stop_reason
            text += "".join(b.text for b in msg.content if b.type == "text")
            if stop == "refusal":
                break
            calls = [b for b in msg.content if b.type == "tool_use"]
            if stop != "tool_use" or not calls:
                break
            messages.append({"role": "assistant", "content": msg.content})  # whole content: keeps thinking blocks
            results = []
            for c in calls:
                if c.name == "submit_answer":
                    submitted = dict(c.input)
                    results.append({"type": "tool_result", "tool_use_id": c.id, "content": "Recorded."})
                    continue
                runs += 1
                ok, out, perr = agent.execute(str(c.input.get("code", "")), timeout=30, inputs=inputs)
                body = (out[-8000:] + ("\n" + perr if perr else "")).strip() or "(no output — print what you need)"
                results.append({"type": "tool_result", "tool_use_id": c.id, "content": body, "is_error": not ok})
            if submitted is not None:
                break
            messages.append({"role": "user", "content": results})
            if turns == self.max_turns - 1:
                messages[-1]["content"].append({"type": "text", "text": "Last turn: submit your final answer now."})
        if submitted is not None:
            text = text.rstrip() + "\nANSWER: " + json.dumps(submitted)
        return Response(text=text, stop_reason=stop, input_tokens=tin, output_tokens=tout,
                        seconds=time.time() - t0, ok=stop != "refusal", error="refusal" if stop == "refusal" else None,
                        extra={"turns": turns, "code_runs": runs, "submitted": submitted is not None})


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


class Local(Provider):
    """An open-weight model behind an OpenAI-compatible /chat/completions endpoint (stdlib HTTP, no SDK)."""

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:1234/v1", images: bool = False,
                 max_tokens: int = 4096, timeout: int = 900):
        self.model, self.base_url, self.max_tokens, self.timeout = model, base_url.rstrip("/"), max_tokens, timeout
        self.supports_images = images
        self.name = f"local:{model}"

    def answer(self, task: Task) -> Response:
        if task.attachments and self.supports_images:
            content: Any = [{"type": "image_url", "image_url": {"url": f"data:{a['media_type']};base64,{a['data']}"}}
                            for a in task.attachments] + [{"type": "text", "text": task.prompt}]
        else:
            content = task.prompt
        body = {"model": self.model, "max_tokens": self.max_tokens, "temperature": 0,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]}
        headers = {"Content-Type": "application/json"}
        if os.environ.get("LOCAL_API_KEY"):
            headers["Authorization"] = "Bearer " + os.environ["LOCAL_API_KEY"]
        req = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(body).encode(), headers=headers)
        t0 = time.time()
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out = json.load(r)
                ch = out["choices"][0]
                usage = out.get("usage") or {}
                return Response(text=ch["message"].get("content") or "", stop_reason=ch.get("finish_reason"),
                                input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
                                seconds=time.time() - t0)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and attempt < 2:
                    time.sleep(2 ** attempt * 3); continue
                return Response(text="", ok=False, error=f"HTTP {e.code}: {e.read()[:300]!r}", seconds=time.time() - t0)
            except (urllib.error.URLError, TimeoutError) as e:
                return Response(text="", ok=False, error=f"connection: {e}", seconds=time.time() - t0)
        return Response(text="", ok=False, error="retries exhausted", seconds=time.time() - t0)


def make(spec: str, effort: str = "high") -> Provider:
    if spec == "oracle":
        return Oracle()
    if spec == "blank":
        return Blank()
    if spec.startswith("local:"):
        rest = spec[len("local:"):]
        images = rest.endswith("+images")
        rest = rest[: -len("+images")] if images else rest
        model, _, url = rest.partition("@")
        return Local(model, url or "http://127.0.0.1:1234/v1", images=images)
    if spec.startswith("ci:"):
        from .agent import Agent
        model, _, url = spec[len("ci:"):].partition("@")
        return Agent(model, url or "http://127.0.0.1:1234/v1")
    if spec.startswith("command:"):
        return Command(spec[len("command:"):])
    if spec.startswith("anthropic:") or spec == "anthropic":
        model, *flags = (spec.split(":", 1)[1] if ":" in spec else "").split("+")
        unknown = set(flags) - {"code", "submit"}
        if unknown:
            raise ValueError(f"unknown anthropic flag(s) {sorted(unknown)} — use +code and/or +submit")
        return Claude(model or "claude-opus-5-5", effort=effort, code="code" in flags, submit="submit" in flags)
    raise ValueError(f"unknown provider {spec!r} — use anthropic:<model>, command:<cmd>, oracle or blank")

