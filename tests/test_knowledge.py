"""Reference cards: which ones a task gets, that they stay out of the way of table contents, and the unit hints."""
import json
import unittest
from pathlib import Path

from constructbench.knowledge import CARDS, _prose, reference, relevant, unit_of

DATA = Path(__file__).resolve().parent.parent / "data"


def names(text):
    return [c.name for c in relevant(text)]


class KnowledgeTests(unittest.TestCase):
    def test_the_matching_card_comes_first(self):
        self.assertEqual(names("Compute the CPI, SPI and EAC from earned value.")[0], "earned value")
        self.assertEqual(names("Manning's n = 0.013, invert to invert")[0], "pipes and drainage")
        self.assertEqual(names("TRIR and DART rate on 200,000 hours")[0], "incident rates")

    def test_acronyms_match_case_sensitively(self):
        self.assertNotIn("zoning", names("By far the largest cost so far is labor."))
        self.assertIn("zoning", names("The lot allows a FAR of 6.0."))

    def test_table_body_rows_do_not_choose_cards(self):
        prompt = "Find the critical path.\n\n| ID | Activity |\n|---|---|\n| A | Roofing |\n| B | Excavate trench |"
        self.assertEqual(_prose(prompt), "Find the critical path.\n\n| ID | Activity |")
        self.assertEqual(names(prompt), ["critical path"])

    def test_no_card_for_unrelated_text_and_reference_says_the_task_wins(self):
        self.assertEqual(reference("Say hello."), "")
        self.assertIn("the task wins", reference("Compute the TRIR."))

    def test_every_card_is_chosen_by_some_task_and_none_is_huge(self):
        used = set()
        # the held-out set is kept private and is not in the public repository, so use whatever is present
        for f in ("dev.jsonl", "heldout-text.jsonl"):
            if not (DATA / f).exists():
                continue
            for line in (DATA / f).read_text().splitlines():
                used.update(names(json.loads(line)["prompt"]))
                self.assertLess(len(reference(json.loads(line)["prompt"])), 2000)
        # families newer than these files: build them from the registry (scheduling covers the expert PDM family)
        from constructbench import registry
        for t in registry.build(seed=1, per_family=2, domains=["quality", "contracts", "civil", "bim", "scheduling"]):
            used.update(names(t.prompt))
        self.assertEqual({c.name for c in CARDS} - used, set())

    def test_bim_tasks_get_their_card_and_file_contents_do_not_choose_cards(self):
        from constructbench import registry
        want = {"clash_detection": "clash detection", "ifc_quantities": "IFC files",
                "asset_register": "COBie and handover data", "file_naming": "ISO 19650 and the CDE",
                "model_5d": "model-based cost and schedule"}
        for fam, card in want.items():
            for t in registry.build(seed=3, per_family=3, families=[fam]):
                self.assertEqual(names(t.prompt)[0], card, fam)
        self.assertEqual(names("Read the file.\n```\n#1=IFCWALL('Brick/Block concrete');\n```"), [])

    def test_unit_hints(self):
        self.assertEqual(unit_of("slope_percent"), "a percent: 12.5 means 12.5%")
        self.assertEqual(unit_of("max_moment_ft_kips"), "foot-kips")
        self.assertEqual(unit_of("required_section_modulus_in3"), "cubic inches")
        self.assertEqual(unit_of("cost_per_sf"), "")
        self.assertEqual(unit_of("open_over_14_days", "array"), "")


if __name__ == "__main__":
    unittest.main()
