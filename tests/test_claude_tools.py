"""The anthropic:<model>+code+submit loop against a scripted fake client — pins the harness, not Claude's skill.

No SDK or key is needed: a stand-in `anthropic` module replays fixed turns (a run_python call, then submit_answer), and
the test checks what the loop sent (strict tools, auto tool choice, thinking kept in history) and what it graded.
"""
import json
import sys
import types
import unittest
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
        self.assertEqual(r.extra, {"turns": 2, "code_runs": 1, "submitted": True})
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


if __name__ == "__main__":
    unittest.main()
