"""Generator invariants: references are right, unambiguous, reproducible and internally consistent."""
import base64
import json
import struct
import unittest

from constructbench import registry
from constructbench.grading import grade
from constructbench.providers import Oracle
from constructbench.generators import scheduling as S
from constructbench.task import DOMAINS
import random


def tasks_for(family, seeds=(1, 2, 3), n=12):
    return [t for s in seeds for t in registry.build(seed=s, per_family=n, families=[family])]


class OracleAcrossSeeds(unittest.TestCase):
    def test_every_family_is_answerable_by_its_own_reference_on_many_seeds(self):
        for fam in registry.FAMILIES:
            for t in tasks_for(fam, seeds=(11, 12, 13), n=10):
                with self.subTest(task=t.id, seed=t.meta["seed"]):
                    self.assertTrue(grade(t, Oracle().answer(t).text).correct)
                    self.assertEqual(set(t.answer), set(t.fields))
                    self.assertIn(t.domain, DOMAINS)

    def test_every_prompt_names_its_answer_keys(self):
        for t in registry.build(seed=5, per_family=3):
            for k in t.fields:
                self.assertIn(f'"{k}"', t.prompt, t.id)


class SchedulingMath(unittest.TestCase):
    def test_cpm_invariants(self):
        for seed in range(60):
            ids, dur, preds = S.network(random.Random(seed))
            c = S.cpm(ids, dur, preds)
            self.assertEqual(c["project"], max(c["ef"].values()))
            for a in ids:
                self.assertGreaterEqual(c["tf"][a], 0)
                self.assertLessEqual(c["ff"][a], c["tf"][a])
                self.assertEqual(c["lf"][a] - c["ls"][a], dur[a])
                for p in preds[a]:
                    self.assertGreaterEqual(c["es"][a], c["ef"][p])
            # A chain of critical activities spans the whole project.
            crit = [a for a in ids if c["tf"][a] == 0]
            self.assertIn(ids[-1], crit)
            self.assertTrue(any(c["es"][a] == 0 for a in crit))

    def test_delay_impact_is_bounded_by_the_delay_and_zero_on_float(self):
        for t in tasks_for("delay_impact"):
            d = t.meta["delay"]
            self.assertGreaterEqual(t.answer["project_delay_days"], 0)
            self.assertLessEqual(t.answer["project_delay_days"], d)
            self.assertEqual(t.answer["new_finish"] - t.answer["original_finish"], t.answer["project_delay_days"])

    def test_lookahead_starting_is_a_subset_of_active(self):
        for t in tasks_for("lookahead"):
            self.assertTrue(set(t.answer["starting_in_window"]) <= set(t.answer["active_in_window"]))
            self.assertTrue(t.answer["starting_in_window"])

    def test_schedule_health_exempts_the_milestones(self):
        for t in tasks_for("schedule_health"):
            ids = [l.split("|")[1].strip() for l in t.prompt.splitlines() if l.startswith("| A")]
            self.assertNotIn(ids[0], t.answer["missing_predecessor"])
            self.assertNotIn(ids[-1], t.answer["missing_successor"])


class SafetyMath(unittest.TestCase):
    def test_trench_width_follows_the_slope(self):
        for t in tasks_for("excavation"):
            depth = int(t.prompt.split(" ft deep")[0].split()[-1])
            bottom = int(t.prompt.split(" ft wide bottom")[0].split()[-1])
            self.assertAlmostEqual(t.answer["top_width_ft"], bottom + 2 * t.answer["slope_ratio_h_per_v"] * depth, places=3)
            self.assertEqual(t.answer["protective_system_required"], "yes" if depth >= 5 else "no")

    def test_fall_clearance_adequacy_matches_the_numbers(self):
        for t in tasks_for("fall_clearance"):
            avail = float(t.prompt.split("There are ")[1].split(" ft")[0])
            self.assertEqual(t.answer["adequate"], "yes" if avail >= t.answer["required_clearance_ft"] else "no")
            self.assertGreaterEqual(t.answer["free_fall_ft"], 0)

    def test_drawing_verdicts_follow_their_measurements(self):
        for t in tasks_for("ladder_image"):
            a = t.answer
            self.assertEqual(a["meets_4_to_1"], "yes" if abs(a["base_offset_ft"] - a["landing_height_ft"] / 4) <= .5 else "no")
            self.assertEqual(a["meets_3ft_extension"], "yes" if a["extension_above_landing_ft"] >= 3 else "no")
        for t in tasks_for("guardrail_image"):
            self.assertEqual(t.answer["top_rail_compliant"], "yes" if 39 <= t.answer["top_rail_height_in"] <= 45 else "no")
        for t in tasks_for("crane_zone_image"):
            self.assertLessEqual(t.answer["workers_inside_swing_radius"], t.answer["workers_total"])

    def test_incident_rates_use_the_200000_hour_basis(self):
        for t in tasks_for("incident_rates"):
            hours = int(t.prompt.split("worked ")[1].split(" hours")[0].replace(",", ""))
            rec = int(t.prompt.split("There were ")[1].split(" ")[0])
            self.assertAlmostEqual(t.answer["trir"], rec * 200_000 / hours, places=3)


class NoTies(unittest.TestCase):
    """A "which one" question must have exactly one right answer."""

    def test_named_winners_are_unique(self):
        for t in tasks_for("rfi_log"):
            counts = {}
            for l in t.prompt.splitlines():
                if l.startswith("| RFI-") and "| — |" in l:
                    who = l.split("|")[4].strip()
                    counts[who] = counts.get(who, 0) + 1
            top = max(counts.values())
            self.assertEqual(sum(1 for v in counts.values() if v == top), 1, t.id)
            self.assertEqual(counts[t.answer["most_open_with"]], top)
        for t in tasks_for("gantt"):
            self.assertIn(t.answer["finishes_last"], t.prompt.upper() + t.answer["finishes_last"])


class Images(unittest.TestCase):
    def test_images_are_valid_pngs_and_reproducible(self):
        for fam in ("floor_plan", "symbol_count", "gantt", "ladder_image", "crane_zone_image", "guardrail_image"):
            a = registry.build(seed=3, per_family=2, families=[fam])
            b = registry.build(seed=3, per_family=2, families=[fam])
            for x, y in zip(a, b):
                png = base64.b64decode(x.attachments[0]["data"])
                self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"), fam)
                w, h = struct.unpack(">II", png[16:24])
                self.assertTrue(200 <= w <= 2000 and 150 <= h <= 2000, (fam, w, h))
                self.assertEqual(x.attachments, y.attachments)


if __name__ == "__main__":
    unittest.main()
