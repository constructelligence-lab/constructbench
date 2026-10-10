"""Quality, contracts and leveling: every answer is re-derived from the prompt text alone, independently of the generator."""
import datetime as dt
import math
import re
import unittest

from constructbench import registry


def fam(name, seeds=(1, 2, 3), n=15):
    return [t for s in seeds for t in registry.build(seed=s, per_family=n, families=[name])]


def table(prompt):
    return [[c.strip() for c in line.strip("|").split("|")] for line in prompt.splitlines()
            if line.startswith("| ") and not line.startswith("| ---") and "---" not in line][1:]


class QualityContracts(unittest.TestCase):
    def test_concrete_acceptance_from_the_table(self):
        outcomes = set()
        for t in fam("concrete_acceptance"):
            fc = int(re.search(r"f'c = ([\d,]+) psi", t.prompt).group(1).replace(",", ""))
            s = [(int(a.replace(",", "")) + int(b.replace(",", ""))) / 2 for _, a, b in table(t.prompt)]
            limit = fc - 500 if fc <= 5000 else 0.9 * fc
            w = [sum(s[k:k + 3]) / 3 for k in range(len(s) - 2)]
            self.assertEqual(t.answer["lowest_test_psi"], min(s))
            self.assertAlmostEqual(t.answer["lowest_three_test_average_psi"], min(w), places=2)
            ok = all(x >= fc for x in w) and all(x >= limit for x in s)
            self.assertEqual(t.answer["acceptable"], "acceptable" if ok else "not acceptable")
            outcomes.add(t.answer["acceptable"])
        self.assertEqual(outcomes, {"acceptable", "not acceptable"})     # both verdicts occur

    def test_compaction_from_the_table(self):
        for t in fam("compaction"):
            spec = int(re.search(r"specified at (\d+)%", t.prompt).group(1))
            band = int(re.search(r"within ±(\d+) percentage", t.prompt).group(1))
            mdd, opt = map(float, re.search(r"density of ([\d.]+) pcf at ([\d.]+)% optimum", t.prompt).groups())
            rows = table(t.prompt)
            rc = {tid: float(wet) / (1 + float(w) / 100) / mdd * 100 for tid, wet, w in rows}
            failing = [tid for tid, wet, w in rows if rc[tid] < spec or abs(float(w) - opt) > band]
            self.assertEqual(t.answer["failing_tests"], failing)
            self.assertAlmostEqual(t.answer["average_relative_compaction_pct"], sum(rc.values()) / len(rc), places=3)

    def test_leveling_carries_the_loop(self):
        for t in fam("leveling"):
            bm = float(re.search(r"elevation ([\d.]+) ft\)", t.prompt).group(1))
            elev, ff = bm, None
            for frm, bs, to, fs in table(t.prompt):
                elev = elev + float(bs) - float(fs)
                if to == "FF-A":
                    ff = elev
            self.assertAlmostEqual(t.answer["ff_a_elevation_ft"], ff, places=3)
            self.assertAlmostEqual(t.answer["misclosure_ft"], elev - bm, places=3)
            ft = int(re.search(r"loop ([\d,]+) ft long", t.prompt).group(1).replace(",", ""))
            c = float(re.search(r"misclosure = ([\d.]+) ×", t.prompt).group(1))
            self.assertAlmostEqual(t.answer["allowable_ft"], c * math.sqrt(ft / 5280), places=4)

    def test_delay_claim_rules(self):
        for t in fam("delay_claim"):
            a = t.answer
            ext = comp = 0
            for _, cause, days, conc in table(t.prompt):
                if cause.startswith(("owner", "unusually")):
                    ext += int(days)
                if cause.startswith("owner"):
                    comp += int(days) - int(conc)
            self.assertEqual((a["extension_days"], a["compensable_days"]), (ext, comp))
            due = dt.date.fromisoformat(re.search(r"completion due (\d{4}-\d\d-\d\d)", t.prompt).group(1))
            actual = dt.date.fromisoformat(re.search(r"achieved on (\d{4}-\d\d-\d\d)", t.prompt).group(1))
            self.assertEqual(a["days_late"], max(0, (actual - due).days - ext))
            self.assertAlmostEqual(a["net_to_contractor"], a["delay_damages"] - a["liquidated_damages"], places=2)

    def test_notice_deadlines_never_on_a_weekend(self):
        for t in fam("notice_deadlines"):
            for key in ("preliminary_notice_deadline", "lien_recording_deadline", "foreclosure_deadline"):
                self.assertLess(dt.date.fromisoformat(t.answer[key]).weekday(), 5)
            recorded = re.search(r"recorded on (\d{4}-\d\d-\d\d)", t.prompt).group(1)
            self.assertLessEqual(recorded, t.answer["lien_recording_deadline"])        # recorded in time
            self.assertGreater(t.answer["days_paid_late"], 0)


if __name__ == "__main__":
    unittest.main()
