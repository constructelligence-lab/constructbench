"""Paired statistics and repeats: known values, and the unit of analysis being the task."""
import json
import tempfile
import unittest
from pathlib import Path

from constructbench.providers import Provider, Response
from constructbench.registry import build
from constructbench.runner import regrade, run
from constructbench.stats import bootstrap_ci, mcnemar_exact, paired, sign_flip_p


def row(tid, ok, rep=0, cost=None):
    return {"task_id": tid, "rep": rep, "grade": {"correct": ok}, "response": {"extra": {} if cost is None else {"cost_usd": cost}}}


class Stats(unittest.TestCase):
    def test_mcnemar_known_values(self):
        self.assertEqual(mcnemar_exact(0, 0), 1.0)
        self.assertAlmostEqual(mcnemar_exact(2, 0), 0.5)
        self.assertAlmostEqual(mcnemar_exact(10, 0), 2 / 1024)
        self.assertAlmostEqual(mcnemar_exact(7, 2), 0.1796875)        # 2 * P(X<=2), X~Bin(9, .5)

    def test_sign_flip_matches_mcnemar_for_single_runs(self):
        self.assertAlmostEqual(sign_flip_p([1] * 7 + [-1] * 2 + [0] * 30), mcnemar_exact(7, 2))

    def test_bootstrap_brackets_the_mean_and_is_deterministic(self):
        d = [0.0] * 20 + [1.0] * 5 + [-1.0]
        lo, hi = bootstrap_ci(d)
        self.assertLess(lo, sum(d) / len(d)); self.assertGreater(hi, sum(d) / len(d))
        self.assertEqual(bootstrap_ci(d), (lo, hi))

    def test_repeats_are_averaged_within_a_task(self):
        a = [row("t1", True, 0), row("t1", True, 1), row("t2", True, 0), row("t2", False, 1)]
        b = [row("t1", False, 0), row("t1", False, 1), row("t2", True, 0), row("t2", True, 1)]
        st = paired(a, b)
        self.assertEqual((st["tasks"], st["runs_a"]), (2, 4))
        self.assertAlmostEqual(st["diff"], (1.0 + (-0.5)) / 2)
        self.assertIsNone(st["p_mcnemar"])                            # not single-run data

    def test_cost_per_correct(self):
        st = paired([row("t1", True, cost=0.2), row("t2", False, cost=0.2)], [row("t1", True, cost=0.1), row("t2", True, cost=0.1)])
        self.assertAlmostEqual(st["cost_per_correct_a"], 0.4)
        self.assertAlmostEqual(st["cost_per_correct_b"], 0.1)


class Repeats(unittest.TestCase):
    def test_repeats_run_resume_and_regrade(self):
        class Flaky(Provider):
            name = "flaky"
            def __init__(self):
                self.n = 0
            def answer(self, task):
                self.n += 1
                return Response(text="ANSWER: " + json.dumps(task.answer) if self.n % 2 else "no")
        tasks = build(seed=1, per_family=1)[:4]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "r.jsonl"
            p = Flaky()
            run(p, tasks, out, workers=1, log=lambda *_: None, repeats=3)
            self.assertEqual(p.n, 12)
            p2 = Flaky()
            run(p2, tasks, out, workers=1, log=lambda *_: None, repeats=3)
            self.assertEqual(p2.n, 0)                                 # everything already done
            rows = regrade(out, tasks)
            self.assertEqual(len(rows), 12)
            self.assertEqual({r["rep"] for r in rows}, {0, 1, 2})


if __name__ == "__main__":
    unittest.main()
