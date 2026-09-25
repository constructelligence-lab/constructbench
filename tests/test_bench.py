"""The harness must be exact before any model score means anything."""
import json
import unittest

from constructbench import registry
from constructbench.grading import extract_answer, grade
from constructbench.providers import Oracle, Blank
from constructbench.task import DOMAINS, Task


class BenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = registry.build(seed=7, per_family=8)

    def test_every_domain_is_covered(self):
        self.assertEqual(set(DOMAINS), {t.domain for t in self.tasks})

    def test_oracle_scores_100_and_blank_scores_0(self):
        for t in self.tasks:
            self.assertTrue(grade(t, Oracle().answer(t).text).correct, t.id)
            self.assertFalse(grade(t, Blank().answer(t).text).parsed, t.id)

    def test_same_seed_same_tasks_and_images(self):
        again = registry.build(seed=7, per_family=8)
        self.assertEqual([json.dumps(t.to_json()) for t in self.tasks], [json.dumps(t.to_json()) for t in again])
        other = registry.build(seed=8, per_family=8)
        self.assertNotEqual(self.tasks[0].prompt, other[0].prompt)

    def test_tasks_round_trip_through_json(self):
        for t in self.tasks[:20]:
            self.assertEqual(Task.from_json(json.loads(json.dumps(t.to_json()))).to_json(), t.to_json())

    def test_answer_extraction_takes_the_last_answer_and_tolerates_formatting(self):
        text = 'Format: ANSWER: {"x": 0}\nWorking...\nANSWER: {"x": "1,250.50", "y": "abc"}.'
        self.assertEqual(extract_answer(text), {"x": "1,250.50", "y": "abc"})
        self.assertIsNone(extract_answer("no answer here"))

    def test_a_wrong_number_fails_and_partial_credit_counts(self):
        t = next(t for t in self.tasks if t.category == "labor")
        wrong = dict(t.answer); wrong["forecast_hours_at_completion"] *= 1.05
        g = grade(t, "ANSWER: " + json.dumps(wrong))
        self.assertFalse(g.correct)
        self.assertAlmostEqual(g.field_score, 3 / 4)

    def test_visual_tasks_carry_png_images(self):
        vis = [t for t in self.tasks if t.domain == "visual_intelligence"]
        self.assertTrue(vis)
        for t in vis:
            self.assertEqual(t.attachments[0]["media_type"], "image/png")
            import base64
            self.assertTrue(base64.b64decode(t.attachments[0]["data"]).startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
