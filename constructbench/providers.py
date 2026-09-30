"""Who answers the tasks.

  anthropic:<model>   Claude via the official `anthropic` SDK (pip install anthropic; credentials from the
                      environment or `ant auth login`). Default model: claude-opus-5.
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
    """
    supports_images = True

    def __init__(self, model: str = "claude-opus-5", effort: str = "high", max_tokens: int = 16000):
        import anthropic  # imported here so the harness itself needs nothing installed
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=4)
        self.model, self.effort, self.max_tokens = model, effort, max_tokens
        self.name = f"anthropic:{model}@{effort}"

    def answer(self, task: Task) -> Response:
        content: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": a["media_type"], "data": a["data"]}}
            for a in task.attachments
        ]
        content.append({"type": "text", "text": task.prompt})
        t0 = time.time()
        a = self._anthropic
        try:
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                messages=[{"role": "user", "content": content}],
            )
        except a.RateLimitError as e:
            return Response(text="", ok=False, error=f"rate limited: {e.message}", seconds=time.time() - t0)
        except a.APIStatusError as e:
            return Response(text="", ok=False, error=f"HTTP {e.status_code}: {e.message}", seconds=time.time() - t0)
        except a.APIConnectionError as e:
            return Response(text="", ok=False, error=f"connection: {e}", seconds=time.time() - t0)
        text = "".join(b.text for b in msg.content if b.type == "text")
        return Response(text=text, stop_reason=msg.stop_reason, input_tokens=msg.usage.input_tokens,
                        output_tokens=msg.usage.output_tokens, seconds=time.time() - t0,
                        ok=msg.stop_reason != "refusal", error="refusal" if msg.stop_reason == "refusal" else None)


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
        model = spec.split(":", 1)[1] if ":" in spec else "claude-opus-5"
        return Claude(model or "claude-opus-5", effort=effort)
    raise ValueError(f"unknown provider {spec!r} — use anthropic:<model>, command:<cmd>, oracle or blank")

