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
        for f in ("dev.jsonl", "heldout-text.jsonl"):
            for line in (DATA / f).read_text().splitlines():
                used.update(names(json.loads(line)["prompt"]))
                self.assertLess(len(reference(json.loads(line)["prompt"])), 2000)
        # quality, contracts and leveling cards are for families newer than these files
        newer = {"concrete acceptance", "compaction", "contract delays", "differential leveling"}
        self.assertEqual({c.name for c in CARDS} - used - newer, set())

    def test_unit_hints(self):
        self.assertEqual(unit_of("slope_percent"), "a percent: 12.5 means 12.5%")
        self.assertEqual(unit_of("max_moment_ft_kips"), "foot-kips")
        self.assertEqual(unit_of("required_section_modulus_in3"), "cubic inches")
        self.assertEqual(unit_of("cost_per_sf"), "")
        self.assertEqual(unit_of("open_over_14_days", "array"), "")


if __name__ == "__main__":
    unittest.main()
