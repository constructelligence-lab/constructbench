"""The construction helpers the ci: agent preloads: PDM relationships with lags, working-day calendars, average-end-area
mass haul, Manning capacity, sequential markups and earned value. Each expected value is hand-computed in the test.
"""
import datetime as dt
import unittest

from constructbench.toolkit import (compound_markups, convert, convert_temp, evm, manning_full, mass_haul, pdm,
                                    station_label, unit_dimension, working_day_date)


class PdmTests(unittest.TestCase):
    def test_fs_ss_and_ff_relationships_with_lags(self):
        """A(5) then B: SS+2, C: FF+1, D: B FS+1 and C FS, E: A SS+1 — the three relationship types all bind."""
        r = pdm([{"id": "A", "duration": 5, "preds": "—"},
                 {"id": "B", "duration": 3, "preds": "A SS+2"},
                 {"id": "C", "duration": 4, "preds": "A FF+1"},
                 {"id": "D", "duration": 2, "preds": "B FS+1, C FS"},
                 {"id": "E", "duration": 3, "preds": "A SS+1"}])
        self.assertEqual(r["duration"], 8)
        self.assertEqual(r["critical"], ["A", "B", "C", "D"])
        # SS+2 puts B's early start at 2; FF+1 pulls C's finish to 6, so C starts at 2; both hold D to 6.
        self.assertEqual([r["by_id"][x]["es"] for x in "ABCDE"], [0, 2, 2, 6, 1])
        self.assertEqual([r["by_id"][x]["tf"] for x in "ABCDE"], [0, 0, 0, 0, 4])

    def test_an_activity_with_no_predecessors_starts_on_day_zero(self):
        r = pdm([{"id": "A010", "duration": 4, "preds": []},
                 {"id": "A020", "duration": 6, "preds": "A010 FF+2"}])
        self.assertEqual(r["by_id"]["A020"]["ef"], 6)          # FF: EF >= EF(A) + 2 = 6
        self.assertEqual(r["by_id"]["A020"]["es"], 0)          # so ES = 6 - 6
        self.assertEqual(r["duration"], 6)

    def test_a_lag_without_a_relationship_means_finish_to_start(self):
        r = pdm([{"id": "A", "duration": 3, "preds": "—"}, {"id": "B", "duration": 2, "preds": "A"}])
        self.assertEqual(r["by_id"]["B"]["es"], 3)
        self.assertEqual(r["duration"], 5)

    def test_a_logic_loop_is_refused(self):
        with self.assertRaises(ValueError):
            pdm([{"id": "A", "duration": 1, "preds": "B"}, {"id": "B", "duration": 1, "preds": "A"}])


class WorkingDayTests(unittest.TestCase):
    def test_day_zero_is_the_first_working_day_and_weekends_are_skipped(self):
        self.assertEqual(working_day_date("2026-01-19", 0), dt.date(2026, 1, 19))   # a Monday
        self.assertEqual(working_day_date("2026-01-19", 4), dt.date(2026, 1, 23))   # Friday
        self.assertEqual(working_day_date("2026-01-19", 5), dt.date(2026, 1, 26))   # Monday, weekend skipped

    def test_holidays_are_skipped_and_never_counted(self):
        self.assertEqual(working_day_date("2026-01-19", 4, ["2026-01-21"]), dt.date(2026, 1, 26))

    def test_a_date_written_with_stray_space_still_parses(self):
        self.assertEqual(working_day_date(" 2026-01-19 ", 1), dt.date(2026, 1, 20))

    def test_accepts_date_objects_and_other_formats(self):
        self.assertEqual(working_day_date(dt.date(2026, 1, 19), 1), dt.date(2026, 1, 20))
        self.assertEqual(working_day_date("01/19/2026", 1), dt.date(2026, 1, 20))


class MassHaulTests(unittest.TestCase):
    def test_average_end_area_with_shrinkage_and_the_peak_ordinate(self):
        """Cut, cut, then fill: the peak is the interior ordinate, and it is NOT the final one."""
        r = mass_haul([300, 300, 0], [0, 0, 300], 50, 0.18, ["10+00", "10+50", "11+00"])
        self.assertAlmostEqual(r["cut_bcy"], 833.3333, places=3)
        self.assertAlmostEqual(r["fill_ccy"], 277.7778, places=3)
        self.assertAlmostEqual(r["max_ordinate"], 455.5556, places=3)
        self.assertEqual(r["max_index"], 1)
        self.assertEqual(r["max_station"], "10+50")
        self.assertAlmostEqual(r["ordinates"][-1], 405.5556, places=3)          # the final ordinate is smaller
        self.assertNotAlmostEqual(r["max_ordinate"], r["ordinates"][-1], places=3)
        self.assertAlmostEqual(r["net_bcy"], 494.5799, places=3)                # final ordinate / (1 - shrink)

    def test_shrinkage_as_a_percent_gives_the_same_answer(self):
        a = mass_haul([300, 300, 0], [0, 0, 300], 50, 0.18)
        b = mass_haul([300, 300, 0], [0, 0, 300], 50, 18)
        self.assertEqual(a["max_ordinate"], b["max_ordinate"])
        self.assertEqual(a["net_bcy"], b["net_bcy"])

    def test_station_labels(self):
        self.assertEqual(station_label(1250), "12+50")
        self.assertEqual(station_label(1000), "10+00")
        self.assertEqual(station_label(1050), "10+50")


class MoneyAndRatesTests(unittest.TestCase):
    def test_markups_compound_in_sequence_never_added_together(self):
        self.assertEqual(compound_markups(100000, [0.08, 0.05]), 113400)
        self.assertEqual(compound_markups(100000, [8, 5]), 113400)      # percent and fraction forms agree
        self.assertNotEqual(compound_markups(100000, [0.08, 0.05]), 113000)

    def test_earned_value_metrics(self):
        self.assertEqual(evm(800000, 720000, 900000, 1600000),
                         {"cpi": 0.8, "spi": 0.9, "cv": -180000, "sv": -80000, "eac": 2000000,
                          "etc": 1100000, "tcpi": 880000 / 700000})

    def test_manning_full_flow_capacity_of_a_12_inch_pipe(self):
        self.assertAlmostEqual(manning_full(12, 0.005, 0.013), 2.52606, places=5)


class UnitConversionTests(unittest.TestCase):
    """Metric/US conversion for international jobs: the model should never hand-convert a length or a pressure."""

    def test_length_area_volume_mass(self):
        self.assertAlmostEqual(convert(12, "in", "mm"), 304.8, places=4)
        self.assertAlmostEqual(convert(1, "m", "ft"), 3.280839895, places=6)
        self.assertAlmostEqual(convert(1200, "sq ft", "m2"), 111.483648, places=5)
        self.assertAlmostEqual(convert(250, "yd3", "m3"), 191.138714496, places=6)
        self.assertAlmostEqual(convert(1, "t", "lb"), 2204.6226218, places=5)

    def test_force_stress_flow(self):
        self.assertAlmostEqual(convert(50, "ksi", "MPa"), 344.7378647, places=5)
        self.assertAlmostEqual(convert(1, "kip", "kN"), 4.4482216, places=5)
        self.assertAlmostEqual(convert(2, "cfs", "m3s"), 0.0566336932, places=8)
        self.assertAlmostEqual(convert(25, "m3h", "l_s"), 6.944444444, places=6)

    def test_spellings_are_accepted_however_they_are_written(self):
        self.assertEqual(convert(1, "CY", "yd3"), 1)
        self.assertAlmostEqual(convert(1, "sf", "ft2"), 1, places=9)
        self.assertAlmostEqual(convert(3, "sq ft", "SF"), 3, places=9)
        self.assertAlmostEqual(convert(2, "ft²", "sqft"), 2, places=9)

    def test_dimension_lookup_and_refusals(self):
        self.assertEqual(unit_dimension("yd3"), "volume")
        self.assertEqual(unit_dimension("ksi"), "stress")
        self.assertIsNone(unit_dimension("banana"))
        with self.assertRaises(ValueError):
            convert(1, "ft", "kg")                     # different dimensions
        with self.assertRaises(ValueError):
            convert(20, "C", "F")                      # temperature is not multiplicative

    def test_temperature(self):
        self.assertAlmostEqual(convert_temp(32, "F", "C"), 0, places=9)
        self.assertAlmostEqual(convert_temp(100, "C", "F"), 212, places=9)
        self.assertAlmostEqual(convert_temp(0, "C", "K"), 273.15, places=9)
        self.assertAlmostEqual(convert_temp(-40, "F", "C"), -40, places=9)


if __name__ == "__main__":
    unittest.main()
