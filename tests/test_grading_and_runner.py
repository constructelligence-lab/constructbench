"""Grader edge cases, the runner, the CLI and the local-model provider (against a fake server)."""
import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from constructbench import registry
from constructbench.cli import main
from constructbench.grading import extract_answer, grade, grade_field
from constructbench.providers import Local, Oracle, Blank, make
from constructbench.runner import run, regrade, summarize, save_tasks, load_tasks, wilson
from constructbench.task import FieldSpec, number, INTEGER, TEXT, DATE, SET, LIST


class Reporting(unittest.TestCase):
    """The published numbers must stay separable: completion, format compliance and strict accuracy are three
    different things, and an API failure is not a wrong answer."""

    def _row(self, ok=True, parsed=True, correct=True, field=1.0):
        return {"task_id": "t", "rep": 0, "domain": "contracts", "category": "notice_deadlines",
                "difficulty": "expert", "provider": "fake",
                "response": {"text": "", "ok": ok, "seconds": 1.0, "output_tokens": 10},
                "grade": {"task_id": "t", "category": "notice_deadlines", "parsed": parsed, "correct": correct,
                          "field_score": field, "fields": {}}}

    def test_an_api_failure_is_not_run_never_a_wrong_answer(self):
        s = summarize([self._row(), self._row(ok=False, parsed=False, correct=False, field=0.0)])
        self.assertEqual(s["not_run"], 1)
        self.assertEqual(s["completion"], 0.5)
        self.assertEqual(s["overall"]["accuracy"], 1.0)          # of the one answer received
        self.assertEqual(s["attempted"], 2)

    def test_format_compliance_is_reported_separately_from_accuracy(self):
        s = summarize([self._row(), self._row(parsed=False, correct=False, field=0.0)])
        self.assertEqual(s["overall"]["format_ok"], 0.5)
        self.assertEqual(s["overall"]["unparsed"], 1)
        self.assertEqual(s["overall"]["accuracy"], 0.5)

    def test_partial_credit_keeps_a_near_miss_out_of_the_zero_bin(self):
        s = summarize([self._row(correct=False, field=0.8)])
        self.assertAlmostEqual(s["overall"]["field_score"], 0.8)
        self.assertEqual(s["overall"]["accuracy"], 0.0)


class LenientGrading(unittest.TestCase):
    """A correct value that skipped the ANSWER line must be visible, but only when asked for."""

    def test_strict_needs_the_answer_line_and_lenient_does_not(self):
        bare = '{"a": 1}'
        self.assertIsNone(extract_answer(bare))
        self.assertEqual(extract_answer(bare, lenient=True), {"a": 1})

    def test_lenient_reads_a_fenced_json_block(self):
        self.assertEqual(extract_answer('here it is:\n```json\n{"a": 1}\n```', lenient=True), {"a": 1})
        self.assertIsNone(extract_answer('here it is:\n```json\n{"a": 1}\n```'))

    def test_lenient_does_not_invent_an_answer_from_prose(self):
        self.assertIsNone(extract_answer("The answer is about 1,250 square feet.", lenient=True))

    def test_strict_still_wins_when_the_answer_line_is_present(self):
        text = 'prose {"wrong": 9}\nANSWER: {"a": 1}'
        self.assertEqual(extract_answer(text), {"a": 1})
        self.assertEqual(extract_answer(text, lenient=True), {"a": 1})


class Grader(unittest.TestCase):
    def test_numbers(self):
        s = number(0.01)
        self.assertTrue(grade_field(s, 100, 100.99))
        self.assertFalse(grade_field(s, 100, 101.5))
        self.assertTrue(grade_field(number(abs_tol=0.5), 0, -0.4))
        self.assertTrue(grade_field(number(0.001), -1250.5, "(1,250.50)"))
        self.assertTrue(grade_field(number(0.001), 12.5, "12.5%"))
        self.assertFalse(grade_field(number(0.001), 1, True))
        self.assertFalse(grade_field(number(0.001), 1, "about one"))

    def test_other_kinds(self):
        self.assertTrue(grade_field(INTEGER, 7, 7.0))
        self.assertFalse(grade_field(INTEGER, 7, 7.2))
        self.assertTrue(grade_field(TEXT, "Voltline Electric", "  voltline   ELECTRIC "))
        self.assertTrue(grade_field(DATE, "2026-09-05", "2026-09-05"))
        self.assertFalse(grade_field(DATE, "2026-09-05", "09/05/2026"))
        self.assertTrue(grade_field(SET, ["A", "B"], ["b", "a"]))
        self.assertFalse(grade_field(SET, ["A", "B"], ["A"]))
        self.assertFalse(grade_field(SET, ["A"], "A"))
        self.assertTrue(grade_field(LIST, ["A", "B"], ["A", "B"]))
        self.assertFalse(grade_field(LIST, ["A", "B"], ["B", "A"]))

    def test_extraction(self):
        self.assertEqual(extract_answer('x\n```\nANSWER: {"a": "}"}\n```'), {"a": "}"})
        self.assertEqual(extract_answer('answer: {"a": 1}'), {"a": 1})
        self.assertIsNone(extract_answer("ANSWER: [1, 2]"))
        self.assertIsNone(extract_answer("ANSWER: {not json}"))
        self.assertIsNone(extract_answer(""))

    def test_keys_are_case_insensitive_and_extras_ignored(self):
        t = registry.build(seed=2, per_family=1, families=["stairs"])[0]
        ans = {k.upper(): v for k, v in t.answer.items()}
        ans["notes"] = "extra"
        self.assertTrue(grade(t, "ANSWER: " + json.dumps(ans)).correct)
        missing = dict(t.answer); missing.pop(next(iter(missing)))
        self.assertFalse(grade(t, "ANSWER: " + json.dumps(missing)).correct)

    def test_wilson_interval(self):
        lo, hi = wilson(0, 10)
        self.assertEqual(lo, 0.0); self.assertGreater(hi, 0.2)
        lo, hi = wilson(10, 10)
        self.assertLess(lo, 1.0); self.assertEqual(hi, 1.0)
        self.assertEqual(wilson(0, 0), (0.0, 0.0))


class TextOnly(Oracle):
    name = "text-only-oracle"
    supports_images = False


class Runner(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tasks = registry.build(seed=4, per_family=2)

    def test_run_is_resumable_and_scores(self):
        out = self.tmp / "o.jsonl"
        run(Oracle(), self.tasks, out, workers=4, log=lambda *_: None)
        first = out.read_text().count("\n")
        run(Oracle(), self.tasks, out, workers=4, log=lambda *_: None)
        self.assertEqual(out.read_text().count("\n"), first)
        s = summarize(regrade(out, self.tasks))
        self.assertEqual(s["overall"]["accuracy"], 1.0)
        self.assertEqual(set(s["domains"]), {t.domain for t in self.tasks})

    def test_text_only_providers_skip_image_tasks(self):
        out = self.tmp / "t.jsonl"
        run(TextOnly(), self.tasks, out, workers=2, log=lambda *_: None)
        ids = {json.loads(l)["task_id"] for l in out.read_text().splitlines()}
        self.assertFalse(any(t.id in ids for t in self.tasks if t.attachments))
        self.assertTrue(all(t.id in ids for t in self.tasks if not t.attachments))

    def test_blank_scores_zero(self):
        out = self.tmp / "b.jsonl"
        run(Blank(), self.tasks, out, workers=2, log=lambda *_: None)
        s = summarize(regrade(out, self.tasks))
        self.assertEqual(s["overall"]["correct"], 0)
        self.assertEqual(s["overall"]["unparsed"], len(self.tasks))

    def test_cli_generate_run_score_leaderboard(self):
        data, res = self.tmp / "d.jsonl", self.tmp / "r.jsonl"
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["generate", "--seed", "9", "--per-family", "1", "--out", str(data)])
            main(["run", "--tasks", str(data), "--provider", "oracle", "--out", str(res), "--workers", "2"])
            main(["leaderboard", str(res), "--tasks", str(data), "--out", str(self.tmp / "L.md")])
        self.assertIn("100.0%", buf.getvalue())
        self.assertIn("| oracle | **100.0%**", (self.tmp / "L.md").read_text())
        blank = self.tmp / "b.jsonl"
        with redirect_stdout(io.StringIO()):
            main(["run", "--tasks", str(data), "--provider", "blank", "--out", str(blank)])
            main(["compare", str(res), str(blank), "--tasks", str(data), "--out", str(self.tmp / "C.md")])
        cmp_ = (self.tmp / "C.md").read_text()
        self.assertIn("+100.0 pts", cmp_)
        self.assertIn("Safety", cmp_)
        self.assertIn("Scheduling", cmp_)

    def test_task_file_round_trip(self):
        p = self.tmp / "x.jsonl"
        save_tasks(self.tasks, p)
        self.assertEqual([t.to_json() for t in load_tasks(p)], [t.to_json() for t in self.tasks])

    def test_provider_specs(self):
        p = make("local:qwen2.5-7b-instruct@http://127.0.0.1:11434/v1")
        self.assertEqual((p.model, p.base_url, p.supports_images), ("qwen2.5-7b-instruct", "http://127.0.0.1:11434/v1", False))
        self.assertTrue(make("local:qwen2.5-vl-7b+images").supports_images)
        with self.assertRaises(ValueError):
            make("gpt:whatever")


class FakeServer(BaseHTTPRequestHandler):
    """An OpenAI-compatible endpoint that answers with the reference, after one 503 when asked to."""
    answers: dict = {}
    fail_once = set()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = body["messages"][-1]["content"]
        prompt = prompt if isinstance(prompt, str) else prompt[-1]["text"]
        tid = next((k for k in self.answers if k in prompt), None)
        if tid in self.fail_once:
            self.fail_once.discard(tid)
            self.send_response(503); self.end_headers(); return
        text = "ANSWER: " + json.dumps(self.answers[tid]) if tid else "no idea"
        out = json.dumps({"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                          "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)

    def log_message(self, *a):
        pass


class LocalProvider(unittest.TestCase):
    def test_local_provider_end_to_end_with_a_retry(self):
        tasks = registry.build(seed=6, per_family=1, families=["stairs", "evm"])
        for t in tasks:                                   # make each prompt findable by id
            t.prompt = f"[{t.id}] " + t.prompt
        FakeServer.answers = {t.id: t.answer for t in tasks}
        FakeServer.fail_once = {tasks[0].id}
        srv = HTTPServer(("127.0.0.1", 0), FakeServer)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            p = Local("fake-model", f"http://127.0.0.1:{srv.server_port}/v1")
            for t in tasks:
                r = p.answer(t)
                self.assertTrue(r.ok, r.error)
                self.assertTrue(grade(t, r.text).correct)
                self.assertEqual(r.output_tokens, 5)
        finally:
            srv.shutdown()

    def test_local_provider_reports_a_dead_server(self):
        t = registry.build(seed=6, per_family=1, families=["stairs"])[0]
        r = Local("x", "http://127.0.0.1:9/v1", timeout=2).answer(t)
        self.assertFalse(r.ok)
        self.assertIn("connection", r.error)


if __name__ == "__main__":
    unittest.main()
