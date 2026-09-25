"""Civil, sustainability and real-estate generators obey their own engineering and finance."""
import math
import re
import unittest

from constructbench import registry


def fam(name, seeds=(1, 2, 3), n=15):
    return [t for s in seeds for t in registry.build(seed=s, per_family=n, families=[name])]


class BuiltWorld(unittest.TestCase):
    def test_earthwork_net_and_direction(self):
        for t in fam("earthwork"):
            a = t.answer
            self.assertAlmostEqual(a["net_cy"], a["fill_cy"] - a["cut_cy"], places=1)
            self.assertEqual(a["import_or_export"], "import" if a["fill_cy"] > a["cut_cy"] else "export")
            self.assertGreaterEqual(min(a["cut_cy"], a["fill_cy"]), 0)

    def test_pipe_capacity_rises_with_slope_and_matches_manning(self):
        for t in fam("gravity_pipe"):
            n = float(re.search(r"n = (\d+\.\d+)", t.prompt).group(1))
            d = int(re.search(r"(\d+) in diameter", t.prompt).group(1)) / 12
            s = t.answer["slope_percent"] / 100
            q = 1.49 / n * (math.pi * d * d / 4) * (d / 4) ** (2 / 3) * math.sqrt(s)
            self.assertAlmostEqual(q, t.answer["full_flow_cfs"], delta=q * 0.002 + 0.001)

    def test_paving_total_includes_waste(self):
        for t in fam("paving"):
            a = t.answer
            self.assertGreater(a["total_tons_with_waste"], a["base_course_tons"] + a["surface_course_tons"])

    def test_carbon_parts_and_intensity(self):
        for t in fam("embodied_carbon"):
            a = t.answer
            gfa = int(t.prompt.split("for a ")[1].split(" m²")[0].replace(",", ""))
            self.assertAlmostEqual(a["kgCO2e_per_m2"], a["total_tCO2e"] * 1000 / gfa, delta=0.01)
            self.assertLess(a["saving_tCO2e"], a["total_tCO2e"])
            self.assertIn(a["largest_contributor"], t.prompt)

    def test_eui_and_solar(self):
        for t in fam("energy_use"):
            self.assertGreater(t.answer["site_eui_kbtu_per_sf"], 0)
        for t in fam("solar_pv"):
            a = t.answer
            self.assertAlmostEqual(a["system_kw_dc"] * 1000 / a["panels"] if a["panels"] else 0,
                                   float(re.search(r"Modules are (\d+) W", t.prompt).group(1)), places=3)
            self.assertGreater(a["simple_payback_years"], 0)

    def test_pro_forma_identities(self):
        for t in fam("pro_forma"):
            a = t.answer
            cap = float(re.search(r"Exit cap rate ([\d.]+)%", t.prompt).group(1)) / 100
            self.assertAlmostEqual(a["stabilized_value"], a["noi"] / cap, delta=1)
            self.assertAlmostEqual(a["yield_on_cost_pct"], a["noi"] / a["total_development_cost"] * 100, delta=0.001)
            self.assertAlmostEqual(a["profit_margin_pct"],
                                   (a["stabilized_value"] - a["total_development_cost"]) / a["total_development_cost"] * 100, delta=0.01)

    def test_lifecycle_verdict_and_maintenance_ranking(self):
        for t in fam("lifecycle_cost"):
            a = t.answer
            self.assertEqual(a["lower_lifecycle_cost"], "A" if a["present_value_cost_a"] < a["present_value_cost_b"] else "B")
        for t in fam("maintenance_priority"):
            a = t.answer
            self.assertEqual(a["top_three"][0], a["top_priority"])
            self.assertEqual(len(a["top_three"]), 3)


if __name__ == "__main__":
    unittest.main()
