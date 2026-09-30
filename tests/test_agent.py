"""The ci: agent — its sandbox, its reading of the answer keys, its vote, and a whole answer against a scripted model.

No model is needed: a stub OpenAI-compatible server replies with fixed programs, so these pin the harness, not a
model's skill. The agent must take the answer shape from the prompt alone — the tests hand it tasks whose grader-side
answer is deliberately wrong, and it must not care.
"""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from constructbench.agent import Agent, answer_keys, coerce, run_program, vote
from constructbench.grading import grade
from constructbench.task import Task


class Stub(BaseHTTPRequestHandler):
    replies: list[str] = []
    seen: list[dict] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Stub.seen.append(body)
        text = Stub.replies.pop(0) if Stub.replies else "```python\nprint(json.dumps({}))\n```"
        out = json.dumps({"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                          "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    def log_message(self, *a):
        pass


def program(d: dict) -> str:
    return "```python\nanswer = " + repr(d) + "\nprint(json.dumps(answer))\n```"


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        Stub.replies, Stub.seen = [], []

    def task(self, answer=None):
        return Task.from_json({"id": "t-0", "domain": "estimating", "category": "c", "title": "t", "difficulty": "easy",
                               "prompt": 'Compute it.\nAnswer keys: "area_sq_ft" (number), "complies" (string).',
                               "answer": answer or {"area_sq_ft": 120, "complies": "yes"},
                               "fields": {"area_sq_ft": {"kind": "number", "rel_tol": 0.005, "abs_tol": 0.5},
                                          "complies": {"kind": "text", "rel_tol": 0, "abs_tol": 0}},
                               "meta": {}, "attachments": []})

    # ── pieces ──
    def test_answer_keys_come_from_the_prompt(self):
        self.assertEqual(answer_keys(self.task().prompt), [("area_sq_ft", "number"), ("complies", "string")])

    def test_sandbox_runs_arithmetic_and_the_stdlib(self):
        res, err = run_program("import statistics, datetime\nprint(json.dumps({'m': statistics.mean([2, 4]), "
                               "'d': str(datetime.date(2026, 1, 2) + datetime.timedelta(days=30))}))")
        self.assertEqual(err, "")
        self.assertEqual(res, {"m": 3, "d": "2026-02-01"})

    def test_sandbox_refuses_files_processes_and_network(self):
        for bad in ["import os\nprint(1)", "import subprocess", "open('/etc/passwd')", "__import__('os')",
                    "import socket", "eval('1')", "from pathlib import Path"]:
            res, err = run_program(bad)
            self.assertIsNone(res, bad)
            self.assertTrue(err, bad)

    def test_sandbox_times_out(self):
        res, err = run_program("while True:\n    pass", timeout=2)
        self.assertIsNone(res)
        self.assertIn("longer than", err)

    def test_vote_takes_the_majority_per_field(self):
        got = vote([{"a": 10.0, "b": "yes"}, {"a": 10.004, "b": "no"}, {"a": 99, "b": "yes"}],
                   [("a", "number"), ("b", "string")])
        self.assertEqual(got, {"a": 10.0, "b": "yes"})

    def test_coerce(self):
        self.assertEqual(coerce("$1,250.50", "number"), 1250.5)
        self.assertEqual(coerce(True, "string"), "yes")
        self.assertIsNone(coerce(True, "number"))

    # ── whole answers ──
    def test_a_correct_program_is_graded_correct(self):
        Stub.replies = [program({"area_sq_ft": 120.0, "complies": "yes"})] * 3
        r = Agent("m", self.url).answer(self.task())
        self.assertTrue(r.ok)
        self.assertTrue(grade(self.task(), r.text).correct, r.text)

    def test_an_error_is_fed_back_and_fixed(self):
        Stub.replies = ["```python\nprint(json.dumps({'area_sq_ft': 1/0}))\n```",
                        program({"area_sq_ft": 120, "complies": "yes"})] + [program({"area_sq_ft": 120, "complies": "yes"})] * 2
        r = Agent("m", self.url).answer(self.task())
        self.assertTrue(grade(self.task(), r.text).correct)
        self.assertIn("ZeroDivisionError", json.dumps(Stub.seen[1]["messages"][-1]))

    def test_one_bad_program_is_outvoted(self):
        Stub.replies = [program({"area_sq_ft": 120, "complies": "yes"}), program({"area_sq_ft": 999, "complies": "no"}),
                        program({"area_sq_ft": 120, "complies": "yes"})]
        self.assertTrue(grade(self.task(), Agent("m", self.url).answer(self.task()).text).correct)

    def test_the_grader_side_answer_is_never_used(self):
        # Same model output, different "true" answer: the agent's reply must not change.
        Stub.replies = [program({"area_sq_ft": 120, "complies": "yes"})] * 3
        a = Agent("m", self.url).answer(self.task()).text
        Stub.replies = [program({"area_sq_ft": 120, "complies": "yes"})] * 3
        b = Agent("m", self.url).answer(self.task(answer={"area_sq_ft": -1, "complies": "no"})).text
        self.assertEqual(a, b)

    def test_nothing_runs_still_gives_an_answer_line(self):
        Stub.replies = ["no code here"] * 12
        r = Agent("m", self.url).answer(self.task())
        self.assertIn("ANSWER: {}", r.text)


if __name__ == "__main__":
    unittest.main()
