"""Robotics generators: the answers obey the geometry and physics they describe."""
import itertools
import math
import random
import re
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

    def test_fleet_allocation_from_prompt(self):
        """Autonomous fleet: the cheapest *feasible* plan, re-derived by exhaustive search from the prompt — and the
        plan that ignores the range limit must be cheaper, since that is the trap the item exists for."""
        for t in fam("fleet_allocation"):
            p = t.prompt
            head = next(l for l in p.splitlines() if l.startswith("| Robot |"))
            tasks = [c.strip() for c in head.strip().strip("|").split("|")][2:]
            table = [[c.strip() for c in row.strip().strip("|").split("|")] for row in p.splitlines()
                     if row.startswith("|")]
            table = [row for row in table if re.fullmatch(r"R\d+", row[0])]
            range_of = {row[0]: int(row[1]) for row in table}
            dist = {(row[0], tasks[k]): int(row[k + 2]) for row in table for k in range(len(tasks))}
            robots = [row[0] for row in table]

            def total(combo, use_range=True):
                if use_range and any(dist[(r, tt)] > range_of[r] for r, tt in zip(combo, tasks)):
                    return None
                return sum(dist[(r, tt)] for r, tt in zip(combo, tasks))

            best_key, best_map = None, None
            for combo in itertools.permutations(robots, len(tasks)):
                tot = total(combo)
                if tot is None:
                    continue
                key = (tot, sorted(f"{r}-{tt}" for r, tt in zip(combo, tasks)))
                if best_key is None or key < best_key:
                    best_key, best_map = key, dict(zip(combo, tasks))
            self.assertEqual(sorted(t.answer["assignment"]), sorted(f"{r}-{tt}" for r, tt in best_map.items()), t.id)
            self.assertEqual(t.answer["total_distance_m"], best_key[0], t.id)
            self.assertEqual(t.answer["makespan_m"], max(dist[(r, tt)] for r, tt in best_map.items()), t.id)
            self.assertEqual(t.answer["idle_robots"], sorted(r for r in robots if r not in best_map), t.id)
            unbounded = min(total(c, use_range=False) for c in itertools.permutations(robots, len(tasks)))
            self.assertGreater(best_key[0], unbounded, t.id)      # ignoring rule 2 gives a cheaper plan

    def test_agv_safety_envelope_from_prompt(self):
        """Autonomous vehicle safety envelope: payload-reduced deceleration, the tolerance in the right units, and
        the speed solved from the zone rather than scaled."""
        for t in fam("agv_safety_envelope"):
            p = t.prompt
            one = lambda pat: float(re.search(pat, p).group(1))   # noqa: E731
            rated = one(r"Rated deceleration ([\d.]+) m/s")
            loss = one(r"costs ([\d.]+)% of that deceleration") / 100
            payload = one(r"payload of (\d+) kg")
            T = one(r"actuation\) is ([\d.]+) s")
            K = one(r"constant is K = ([\d.]+) m/s")
            C = one(r"tolerance is C = (\d+) mm")
            zone = one(r"reaches (\d+) mm")
            v = one(r"under consideration is ([\d.]+) m/s")
            a = rated * (1 - loss * payload)
            gap = zone / 1000.0 - K * T - C / 1000.0
            self.assertAlmostEqual(t.answer["deceleration_loaded_mps2"], round(a, 4), places=4, msg=t.id)
            self.assertAlmostEqual(t.answer["stopping_distance_mm"],
                                   round((K * T + v * v / (2 * a) + C / 1000.0) * 1000, 1), places=1, msg=t.id)
            self.assertEqual(t.answer["permitted"],
                             "yes" if zone >= t.answer["stopping_distance_mm"] else "no", t.id)
            self.assertAlmostEqual(t.answer["max_permitted_speed_mps"],
                                   round(math.sqrt(2 * a * gap), 4), places=3, msg=t.id)


if __name__ == "__main__":
    unittest.main()
