"""The contamination check flags leaked items, and only leaked items."""
import json
import tempfile
import unittest
from pathlib import Path

from constructbench import registry
from constructbench.decontam import check


class Decontam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = registry.build(seed=1, per_family=2)
        cls.dir = Path(tempfile.mkdtemp())

    def corpus(self, rows):
        path = self.dir / f"c{len(rows)}.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return [path]

    def test_leaked_items_are_flagged_even_short_ones(self):
        leaked = [t for t in self.tasks if t.category in ("stairs", "occupancy_egress", "delay_claim")]
        report = check(self.tasks, self.corpus([{"messages": [{"role": "user", "content": t.prompt}]} for t in leaked]))
        self.assertEqual(set(report["task_ids"]), {t.id for t in leaked})

    def test_templates_and_units_do_not_flag(self):
        fresh = registry.build(seed=99, per_family=2)              # same templates, different numbers
        rows = [{"prompt": t.prompt} for t in fresh] + [{"code": 'print(json.dumps(x, indent=2)) # 2 2 2 2 m2 co2e'}]
        self.assertEqual(check(self.tasks, self.corpus(rows))["contaminated"], 0)


if __name__ == "__main__":
    unittest.main()
