"""`report`: tables and well-formed SVGs from a synthetic results folder; failure categories on known cases."""
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from constructbench.registry import build
from constructbench.report import build as build_report, classify, parse_provider
from constructbench.runner import save_tasks


def row(t, provider, text, rep=0, cost=0.01, stop="end_turn"):
    from constructbench.grading import grade
    from dataclasses import asdict
    return {"task_id": t.id, "rep": rep, "domain": t.domain, "category": t.category, "difficulty": t.difficulty,
            "provider": provider, "response": {"text": text, "ok": True, "error": None, "stop_reason": stop,
                                                "output_tokens": 100, "seconds": 1.0, "extra": {"cost_usd": cost}},
            "grade": asdict(grade(t, text))}


class Report(unittest.TestCase):
    def test_parse_provider(self):
        self.assertEqual(parse_provider("anthropic:claude-haiku-5-5+code+submit@low"), ("claude-haiku-5-5", "harness", "low"))
        self.assertEqual(parse_provider("anthropic:claude-opus-5-5@high"), ("claude-opus-5-5", "base", "high"))
        self.assertEqual(parse_provider("api:deepseek-chat+code"), ("deepseek-chat", "code", "—"))

    def test_classify_known_failures(self):
        t = next(t for t in build(seed=1, per_family=1) if t.category == "pay_app_certification")
        ok = row(t, "x", "ANSWER: " + json.dumps(t.answer))
        self.assertIsNone(classify(ok, t))
        prose = dict(t.answer, error_lines=["Item 4 has the wrong total completed and stored figure"])
        self.assertEqual(classify(row(t, "x", "ANSWER: " + json.dumps(prose)), t), "format: prose in ID list")
        near = dict(t.answer, retainage=t.answer["retainage"] * 1.005)
        self.assertEqual(classify(row(t, "x", "ANSWER: " + json.dumps(near)), t), "near miss (≤1%)")
        far = dict(t.answer, retainage=t.answer["retainage"] * 1.3)
        self.assertEqual(classify(row(t, "x", "ANSWER: " + json.dumps(far)), t), "numeric error (>1%)")
        self.assertEqual(classify(row(t, "x", "", stop="max_tokens"), t), "no answer: out of tokens")

    def test_build_writes_tables_and_valid_svgs(self):
        tasks = build(seed=1, per_family=1)[:12]
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            save_tasks(tasks, d / "data" / "mini.jsonl")
            res = d / "results" / "mini"; res.mkdir(parents=True)
            for prov, good in (("anthropic:claude-haiku-5-5@high", 9), ("anthropic:claude-haiku-5-5+code+submit@high", 11)):
                with (res / (prov.replace(":", "_") + ".jsonl")).open("w") as f:
                    for k, t in enumerate(tasks):
                        f.write(json.dumps(row(t, prov, "ANSWER: " + json.dumps(t.answer) if k < good else "no")) + "\n")
            md = build_report([res], d / "data", d / "out")
            text = md.read_text()
            self.assertIn("| mini | claude-haiku-5-5 | Harness (code + submit) | high | 12 | 12 | 91.7%", text)
            self.assertIn("+16.7", text)                                   # 11/12 vs 9/12, paired
            for svg in (d / "out").glob("*.svg"):
                ET.parse(svg)                                              # well-formed XML
            self.assertEqual(len(list((d / "out").glob("*.svg"))), 4)


if __name__ == "__main__":
    unittest.main()
