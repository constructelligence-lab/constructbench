"""The anthropic:<model>+code+submit loop against a scripted fake client — pins the harness, not Claude's skill.

No SDK or key is needed: a stand-in `anthropic` module replays fixed turns (a run_python call, then submit_answer), and
the test checks what the loop sent (strict tools, auto tool choice, thinking kept in history) and what it graded.
"""
import json
import sys
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace as NS

from constructbench.grading import grade
from constructbench.providers import answer_schema, make
from constructbench.registry import build


def _usage(out=10):
    return NS(input_tokens=100, output_tokens=out, cache_read_input_tokens=0, cache_creation_input_tokens=0)


class FakeMessages:
    def __init__(self, turns):
        self.turns, self.calls = list(turns), []

    def create(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=lambda o: o.__dict__)))
        return self.turns.pop(0)


def fake_anthropic(turns):
    mod = types.ModuleType("anthropic")
    msgs = FakeMessages(turns)
    mod.Anthropic = lambda **kw: NS(messages=msgs)
    for n in ("RateLimitError", "APIStatusError", "APIConnectionError"):
        setattr(mod, n, type(n, (Exception,), {}))
    return mod, msgs


def tool_use(id_, name, inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


class ClaudeToolLoop(unittest.TestCase):
    def setUp(self):
        self.task = next(t for t in build(seed=1, per_family=1) if t.id.startswith("arch-far"))
        self._saved = sys.modules.get("anthropic")

    def tearDown(self):
        if self._saved is None:
            sys.modules.pop("anthropic", None)
        else:
            sys.modules["anthropic"] = self._saved

    def run_with(self, turns, spec="anthropic:claude-opus-5-5+code+submit"):
        mod, msgs = fake_anthropic(turns)
        sys.modules["anthropic"] = mod
        p = make(spec)
        return p, p.answer(self.task), msgs

    def test_code_then_submit_is_graded(self):
        right = self.task.answer
        turns = [
            NS(stop_reason="tool_use", usage=_usage(), content=[
                NS(type="thinking", thinking="", signature="sig"),
                tool_use("t1", "run_python", {"code": "print(6 * 7)"})]),
            NS(stop_reason="tool_use", usage=_usage(), content=[tool_use("t2", "submit_answer", right)]),
        ]
        p, r, msgs = self.run_with(turns)
        self.assertEqual(p.name, "anthropic:claude-opus-5-5+code+submit@high")
        self.assertTrue(grade(self.task, r.text).correct)
        self.assertEqual(r.extra, {"turns": 2, "code_runs": 1, "submitted": True, "rejected_submits": 0})
        first, second = msgs.calls
        self.assertEqual(first["tool_choice"], {"type": "auto"})
        self.assertEqual(first["output_config"], {"effort": "high"})
        self.assertTrue(all(t["strict"] for t in first["tools"]))
        sub = next(t for t in first["tools"] if t["name"] == "submit_answer")
        self.assertEqual(set(sub["input_schema"]["required"]), set(right))
        # the whole assistant turn (thinking included) goes back, then the tool result with the program's stdout
        self.assertEqual(second["messages"][1]["content"][0]["type"], "thinking")
        result = second["messages"][2]["content"][0]
        self.assertEqual((result["tool_use_id"], result["content"].strip(), result["is_error"]), ("t1", "42", False))

    def test_sandbox_errors_go_back_as_tool_errors(self):
        turns = [
            NS(stop_reason="tool_use", usage=_usage(), content=[tool_use("t1", "run_python", {"code": "import os"})]),
            NS(stop_reason="end_turn", usage=_usage(), content=[NS(type="text", text="ANSWER: {}")]),
        ]
        _, r, msgs = self.run_with(turns)
        result = msgs.calls[1]["messages"][2]["content"][0]
        self.assertTrue(result["is_error"])
        self.assertIn("not available", result["content"])
        self.assertFalse(r.extra["submitted"])

    def test_plain_spec_is_one_call_without_tools(self):
        turns = [NS(stop_reason="end_turn", usage=_usage(), content=[NS(type="text", text="ANSWER: {}")])]
        p, r, msgs = self.run_with(turns, "anthropic:claude-opus-5-5")
        self.assertEqual(p.name, "anthropic:claude-opus-5-5@high")
        self.assertNotIn("tools", msgs.calls[0])

    def test_unknown_flag_rejected(self):
        sys.modules["anthropic"] = fake_anthropic([])[0]
        with self.assertRaises(ValueError):
            make("anthropic:claude-opus-5-5+cheat")

    def test_schema_types(self):
        s = answer_schema([("a", "number"), ("b", "integer"), ("c", "string"), ("d", "array"), ("e", "date")])
        self.assertEqual([s["properties"][k]["type"] for k in "abcde"], ["number", "integer", "string", "array", "string"])
        self.assertFalse(s["additionalProperties"])




class Script(BaseHTTPRequestHandler):
    """An OpenAI-compatible server that replays scripted assistant messages and records each request body."""
    replies: list = []
    seen: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Script.seen.append({"body": body, "auth": self.headers.get("Authorization")})
        msg = Script.replies.pop(0)
        out = json.dumps({"choices": [{"message": msg, "finish_reason": "tool_calls" if msg.get("tool_calls") else "stop"}],
                          "usage": {"prompt_tokens": 50, "completion_tokens": 5}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    def log_message(self, *a):
        pass


def call(id_, name, args):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class OpenAICompatibleToolLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Script)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}/v1"
        cls.task = next(t for t in build(seed=1, per_family=1) if t.id.startswith("arch-far"))

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def test_bad_submit_is_sent_back_once_then_graded(self):
        right = self.task.answer
        first = dict(right); first.pop(next(iter(first)))           # one key missing
        Script.seen, Script.replies = [], [
            {"role": "assistant", "content": None, "reasoning_content": "r1",
             "tool_calls": [call("c1", "run_python", {"code": "print(TABLES)"})]},
            {"role": "assistant", "content": None, "tool_calls": [call("c2", "submit_answer", first)]},
            {"role": "assistant", "content": None, "tool_calls": [call("c3", "submit_answer", right)]},
        ]
        p = make(f"local:test-model@{self.url}+code+submit")
        self.assertEqual(p.name, "local:test-model+code+submit")
        r = p.answer(self.task)
        self.assertTrue(grade(self.task, r.text).correct)
        self.assertEqual(r.extra, {"turns": 3, "code_runs": 1, "submitted": True, "rejected_submits": 1})
        sent = Script.seen[1]["body"]["messages"]
        self.assertEqual(sent[2]["reasoning_content"], "r1")         # thinking echoed back within the turn
        self.assertEqual((sent[3]["role"], sent[3]["content"].strip()), ("tool", "[]"))
        self.assertIn("missing", Script.seen[2]["body"]["messages"][-1]["content"])
        self.assertEqual({t["function"]["name"] for t in Script.seen[0]["body"]["tools"]}, {"run_python", "submit_answer"})

    def test_hosted_api_needs_its_key(self):
        import os
        old = {k: os.environ.pop(k, None) for k in ("LOCAL_API_KEY", "DEEPSEEK_API_KEY")}
        try:
            with self.assertRaises(ValueError):
                make("api:deepseek-chat@https://api.deepseek.com/v1")
            os.environ["DEEPSEEK_API_KEY"] = "k"
            self.assertEqual(make("api:deepseek-chat@https://api.deepseek.com/v1+code+submit").name,
                             "api:deepseek-chat+code+submit")
        finally:
            os.environ.pop("DEEPSEEK_API_KEY", None)
            os.environ.update({k: v for k, v in old.items() if v})


class FailedCallsAreRetried(unittest.TestCase):
    def test_rerun_replaces_api_failure(self):
        import tempfile
        from pathlib import Path
        from constructbench.providers import Oracle, Provider, Response
        from constructbench.runner import regrade, run

        class Down(Provider):
            name = "down"
            def answer(self, task):
                return Response(text="", ok=False, error="rate limited")

        tasks = build(seed=1, per_family=1)[:3]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "r.jsonl"
            run(Down(), tasks, out, workers=1, log=lambda *_: None)
            run(Oracle(), tasks, out, workers=1, log=lambda *_: None)   # same file: only the failures run again
            rows = regrade(out, tasks)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r["grade"]["correct"] for r in rows))


if __name__ == "__main__":
    unittest.main()
