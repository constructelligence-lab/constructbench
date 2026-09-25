"""Robotics generators: the answers obey the geometry and physics they describe."""
import itertools
import math
import random
import unittest

from constructbench import registry
from constructbench.generators import robotics as R


def fam(name, seeds=(1, 2, 3, 4), n=15):
    return [t for s in seeds for t in registry.build(seed=s, per_family=n, families=[name])]


def brute_shortest(grid, start, goal, limit=400):
    """Independent check of the BFS: Dijkstra-free relaxation over all cells until stable."""
    h, w = len(grid), len(grid[0])
    INF = 10 ** 9
    d = {(x, y): INF for y in range(h) for x in range(w) if not grid[y][x]}
    d[start] = 0
    for _ in range(limit):
        changed = False
        for (x, y), v in list(d.items()):
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) in d and d[(nx, ny)] + 1 < v:
                    d[(x, y)] = v = d[(nx, ny)] + 1
                    changed = True
        if not changed:
            break
    return None if d[goal] >= INF else d[goal]


class Robotics(unittest.TestCase):
    def test_bfs_matches_an_independent_search_and_finds_unreachable_goals(self):
        unreachable = 0
        for seed in range(80):
            rng = random.Random(seed)
            w, h = rng.randint(6, 12), rng.randint(5, 9)
            grid = [[1 if rng.random() < .3 else 0 for _ in range(w)] for _ in range(h)]
            free = [(x, y) for y in range(h) for x in range(w) if not grid[y][x]]
            if len(free) < 2:
                continue
            s, g = free[0], free[-1]
            got = R._bfs(grid, s, g)
            self.assertEqual(got, brute_shortest(grid, s, g), seed)
            unreachable += got is None
        self.assertGreater(unreachable, 0)          # the check exercises both outcomes

    def test_path_answers_are_self_consistent(self):
        tasks = fam("path_planning", seeds=range(1, 9), n=15)
        # Walls without a door gap make some goals unreachable — the set must contain both outcomes.
        self.assertTrue(any(t.answer["reachable"] == "no" for t in tasks))
        self.assertTrue(any(t.answer["reachable"] == "yes" for t in tasks))
        for t in tasks:
            a = t.answer
            if a["reachable"] == "no":
                self.assertEqual((a["shortest_path_cells"], a["shortest_path_m"]), (0, 0))
            else:
                self.assertGreater(a["shortest_path_cells"], 0)
            self.assertTrue(t.attachments)

    def test_layout_transform_preserves_distance(self):
        for t in fam("layout_transform"):
            nums = [float(x) for x in __import__("re").findall(r"x = ([\d.]+), y = ([\d.]+)", t.prompt)[0]]
            e0 = float(t.prompt.split("E = ")[1].split(",")[0]); n0 = float(t.prompt.split("N = ")[1].split(",")[0])
            self.assertAlmostEqual(math.hypot(t.answer["point1_easting"] - e0, t.answer["point1_northing"] - n0),
                                   math.hypot(*nums), places=3)

    def test_arm_tip_is_within_reach_of_its_own_links(self):
        for t in fam("kinematics"):
            base = float(t.prompt.split("joint is ")[1].split(" m")[0])
            l1 = float(t.prompt.split("Link 1 is ")[1].split(" m")[0]); l2 = float(t.prompt.split("link 2 is ")[1].split(" m")[0])
            d = math.hypot(t.answer["tip_x_m"], t.answer["tip_y_m"] - base)
            self.assertLessEqual(d, l1 + l2 + 1e-6)
            self.assertGreaterEqual(d, abs(l1 - l2) - 1e-6)

    def test_drone_lines_cover_the_site(self):
        for t in fam("drone_survey"):
            width = int(t.prompt.split("over a ")[1].split(" m")[0])
            a = t.answer
            self.assertGreaterEqual((a["flight_lines"] - 1) * a["line_spacing_m"], width - 1e-6)
            self.assertLess(a["line_spacing_m"], a["footprint_width_m"])
            per = int(t.prompt.split("each battery gives ")[1].split(" minutes")[0])
            self.assertGreaterEqual(a["batteries"] * per, a["flight_minutes"])
            self.assertLess((a["batteries"] - 1) * per, a["flight_minutes"])

    def test_rebar_and_bricks(self):
        for t in fam("rebar_tying"):
            a = t.answer
            inter = a["bars_long_direction"] * a["bars_short_direction"]
            self.assertIn(a["ties"], (inter, math.ceil(inter / 2)))
            self.assertLess(a["robot_hours"], a["crew_hours"] * 10)
        for t in fam("bricklaying"):
            a = t.answer
            self.assertEqual(a["faster"], "robot" if a["robot_days"] < a["crew_days"] else "crew")
            self.assertEqual(a["bricks"], math.ceil(a["net_wall_area_sf"] * 6.86))


if __name__ == "__main__":
    unittest.main()
