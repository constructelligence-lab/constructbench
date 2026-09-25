"""Construction robotics: navigation, layout, kinematics, drone survey planning, and robot productivity.

The math a robotics engineer or a site team deploying robots actually does: can the robot get there and how far,
where does a drawing point land on site, where is the arm's tip, how many flight lines and batteries, how long does
a tying or bricklaying robot take compared with a crew. Conventions are stated so each task has one answer.
"""
from __future__ import annotations

import math
import random
from collections import deque

from ..task import Task, number, INTEGER, TEXT, answer_keys_line
from ..render import Canvas
from .common import pick


def _bfs(grid, start, goal):
    h, w = len(grid), len(grid[0])
    dist = {start: 0}
    q = deque([start])
    while q:
        x, y = q.popleft()
        if (x, y) == goal:
            return dist[(x, y)]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not grid[ny][nx] and (nx, ny) not in dist:
                dist[(nx, ny)] = dist[(x, y)] + 1
                q.append((nx, ny))
    return None


def path_planning(rng: random.Random, i: int) -> Task:
    """An occupancy grid rendered as an image: shortest 4-connected path, or unreachable; free floor area."""
    w, h = rng.randint(12, 18), rng.randint(9, 13)
    cell_m = rng.choice([0.5, 1.0])
    grid = [[0] * w for _ in range(h)]
    # Walls with door gaps, plus scattered obstacles (columns, material stacks).
    for _ in range(rng.randint(2, 4)):
        if rng.random() < .5:
            x = rng.randint(2, w - 3)
            gap = rng.randint(0, h - 1) if rng.random() < .8 else None
            for y in range(h):
                grid[y][x] = 0 if y == gap else 1
        else:
            y = rng.randint(2, h - 3)
            gap = rng.randint(0, w - 1) if rng.random() < .8 else None
            for x in range(w):
                grid[y][x] = 0 if x == gap else 1
    for _ in range(rng.randint(4, 14)):
        grid[rng.randrange(h)][rng.randrange(w)] = 1
    free = [(x, y) for y in range(h) for x in range(w) if not grid[y][x]]
    if len(free) < 10:
        return path_planning(rng, i)
    start = free[rng.randrange(len(free))]
    goal = free[rng.randrange(len(free))]
    if start == goal:
        return path_planning(rng, i)
    steps = _bfs(grid, start, goal)
    cell, m = 36, 40
    cv = Canvas(m * 2 + w * cell, m * 2 + h * cell + 40)
    oy = m + 40
    for y in range(h):
        for x in range(w):
            x0, y0 = m + x * cell, oy + y * cell
            if grid[y][x]:
                cv.fill(x0, y0, x0 + cell, y0 + cell, v=40)
            cv.rect(x0, y0, x0 + cell, y0 + cell, v=200)
    for (px, py), lab in ((start, "S"), (goal, "G")):
        cv.text(m + px * cell + 11, oy + py * cell + 8, lab, scale=3)
    cv.rect(m, oy, m + w * cell, oy + h * cell, t=3)
    cv.text(m, 12, f"OCCUPANCY GRID  1 CELL = {cell_m:g} M", scale=2)
    cv.text(m, 34, "DARK = BLOCKED", scale=2)
    fields = {"reachable": TEXT, "shortest_path_cells": INTEGER, "shortest_path_m": number(abs_tol=0.01), "free_area_m2": number(abs_tol=0.01)}
    prompt = ("The attached image is an occupancy grid of a floor for a layout robot: dark cells are blocked (walls, columns, "
              "material), light cells are free; S is the robot, G is the target. The robot moves one cell at a time up, down, "
              "left or right (no diagonals) through free cells. Say whether G is reachable (\"yes\"/\"no\"); if it is, give the "
              "fewest moves and that distance in metres (moves × cell size); if not, give 0 for both. Also give the total free "
              "floor area in m² (free cells × cell area).\n" + answer_keys_line(fields))
    return Task(f"rob-path-{i:04d}", "robotics", "path_planning", "Robot path on an occupancy grid", "hard", prompt,
                {"reachable": "yes" if steps is not None else "no", "shortest_path_cells": steps or 0,
                 "shortest_path_m": round((steps or 0) * cell_m, 3), "free_area_m2": round(len(free) * cell_m ** 2, 3)},
                fields, {}, [cv.attachment(f"grid-{i}.png")])


def layout_transform(rng: random.Random, i: int) -> Task:
    theta = rng.choice([0, 15, 22.5, 30, 45, 60, 90, 127.5, 180, 270, 315])
    e0, n0 = round(rng.uniform(1000, 5000), 3), round(rng.uniform(1000, 5000), 3)
    p1 = (round(rng.uniform(0, 120), 2), round(rng.uniform(0, 90), 2))
    p2 = (round(rng.uniform(0, 120), 2), round(rng.uniform(0, 90), 2))
    t = math.radians(theta)
    def site(p):
        return e0 + p[0] * math.cos(t) - p[1] * math.sin(t), n0 + p[0] * math.sin(t) + p[1] * math.cos(t)
    s1 = site(p1)
    dist = math.dist(p1, p2)
    fields = {"point1_easting": number(abs_tol=0.005), "point1_northing": number(abs_tol=0.005), "distance_p1_p2": number(abs_tol=0.005)}
    prompt = (f"A layout robot works in site coordinates (easting E, northing N, in feet). The building grid origin sits at "
              f"E = {e0}, N = {n0}, and the building's x-axis is rotated {theta}° counter-clockwise from site east (its y-axis is "
              "90° counter-clockwise from its x-axis). So E = E0 + x·cosθ − y·sinθ and N = N0 + x·sinθ + y·cosθ.\n"
              f"Anchor point 1 is at building coordinates x = {p1[0]}, y = {p1[1]}; point 2 at x = {p2[0]}, y = {p2[1]}. "
              "Give point 1's easting and northing, and the straight-line distance between the two points.\n" + answer_keys_line(fields))
    return Task(f"rob-layout-{i:04d}", "robotics", "layout_transform", "Layout robot coordinate transform", "medium", prompt,
                {"point1_easting": round(s1[0], 4), "point1_northing": round(s1[1], 4), "distance_p1_p2": round(dist, 4)}, fields)


def arm(rng: random.Random, i: int) -> Task:
    kind = pick(rng, ["excavator boom and stick", "two-link robotic arm"])
    l1, l2 = round(rng.uniform(2.0, 6.5), 2), round(rng.uniform(1.2, 4.0), 2)
    base_h = round(rng.uniform(0.8, 2.2), 2)
    a1, a2 = rng.randint(10, 70), rng.randint(-120, -10)       # a2 relative to link 1
    x = l1 * math.cos(math.radians(a1)) + l2 * math.cos(math.radians(a1 + a2))
    y = base_h + l1 * math.sin(math.radians(a1)) + l2 * math.sin(math.radians(a1 + a2))
    tx, ty = round(rng.uniform(0.5, l1 + l2 + 1.5), 2), round(rng.uniform(-1, 4), 2)
    d = math.hypot(tx, ty - base_h)
    reachable = abs(l1 - l2) <= d <= l1 + l2
    fields = {"tip_x_m": number(abs_tol=0.01), "tip_y_m": number(abs_tol=0.01), "target_reachable": TEXT}
    prompt = (f"A {kind} works in a vertical plane. The first joint is {base_h} m above the ground at x = 0. Link 1 is {l1} m "
              f"long and link 2 is {l2} m. Joint 1 is at {a1}° above horizontal; joint 2 is at {a2}° measured from link 1's "
              "direction (negative is downward). Give the tip's horizontal position x and height y (metres, y measured from the "
              f"ground), and whether a target at x = {tx} m, height {ty} m can be reached by some joint configuration "
              "(\"yes\"/\"no\"; reachable when its distance from joint 1 is between |L1 − L2| and L1 + L2).\n" + answer_keys_line(fields))
    return Task(f"rob-arm-{i:04d}", "robotics", "kinematics", "Arm forward kinematics and reach", "medium", prompt,
                {"tip_x_m": round(x, 4), "tip_y_m": round(y, 4), "target_reachable": "yes" if reachable else "no"}, fields)


def drone_survey(rng: random.Random, i: int) -> Task:
    width, length = rng.randint(150, 900), rng.randint(200, 1500)
    alt = rng.choice([40, 60, 80, 100, 120])
    fov = rng.choice([60, 73.7, 84])
    side = rng.choice([60, 70, 75, 80])
    speed = rng.choice([5, 8, 10, 12])
    batt = rng.choice([18, 22, 25, 30])
    foot = 2 * alt * math.tan(math.radians(fov / 2))
    spacing = foot * (1 - side / 100)
    lines = math.ceil(width / spacing) + 1
    dist = lines * length + (lines - 1) * spacing
    minutes = dist / speed / 60
    batteries = math.ceil(minutes / batt)
    fields = {"footprint_width_m": number(abs_tol=0.05), "line_spacing_m": number(abs_tol=0.05), "flight_lines": INTEGER,
              "flight_minutes": number(0.005, 0.1), "batteries": INTEGER}
    prompt = (f"Plan a drone mapping flight over a {width} m × {length} m site at {alt} m altitude. The camera's horizontal field "
              f"of view across the flight line is {fov}°. Use {side}% side overlap.\n"
              "Image footprint width = 2 × altitude × tan(FOV/2). Line spacing = footprint × (1 − side overlap). Flight lines run "
              f"along the {length} m side: number of lines = ceil(width ÷ spacing) + 1. Flight distance = lines × {length} m + "
              f"(lines − 1) × spacing for the turns. The drone flies at {speed} m/s and each battery gives {batt} minutes of survey "
              "flight. Give the footprint width, line spacing, number of lines, flight minutes and batteries needed (rounded up).\n"
              + answer_keys_line(fields))
    return Task(f"rob-drone-{i:04d}", "robotics", "drone_survey", "Drone survey flight plan", "medium", prompt,
                {"footprint_width_m": round(foot, 3), "line_spacing_m": round(spacing, 3), "flight_lines": lines,
                 "flight_minutes": round(minutes, 3), "batteries": batteries}, fields)


def rebar_tying(rng: random.Random, i: int) -> Task:
    L, W = rng.randint(40, 240), rng.randint(30, 160)           # ft
    s_long, s_trans = rng.choice([6, 8, 10, 12]), rng.choice([6, 8, 10, 12])   # in
    cover = rng.choice([2, 3])                                   # in, to the first bar at each edge
    pattern = rng.choice(["every intersection", "every other intersection"])
    rate = rng.choice([900, 1100, 1300])                         # ties/hour for the robot
    crew_rate = rng.choice([300, 350, 400])                      # ties/hour per ironworker
    crew = rng.choice([2, 3, 4])
    # Bars running the long way are spaced across the width, and vice versa.
    n_long = math.floor((W * 12 - 2 * cover) / s_long) + 1
    n_trans = math.floor((L * 12 - 2 * cover) / s_trans) + 1
    inter = n_long * n_trans
    ties = inter if pattern == "every intersection" else math.ceil(inter / 2)
    robot_h = ties / rate
    crew_h = ties / (crew_rate * crew)
    fields = {"bars_long_direction": INTEGER, "bars_short_direction": INTEGER, "ties": INTEGER,
              "robot_hours": number(0.002, 0.01), "crew_hours": number(0.002, 0.01)}
    prompt = (f"A rebar-tying robot will tie a single bridge-deck mat {L} ft × {W} ft. Bars running the long way are at {s_long} in "
              f"spacing; bars running the short way at {s_trans} in. The first and last bar each sit {cover} in in from the edges; "
              "bars per direction = floor((dimension across them − 2 × cover) ÷ spacing) + 1 (work in inches). Tie "
              f"{pattern} (every other = half, rounded up). The robot ties {rate:,} intersections an hour; a crew of {crew} "
              f"ironworkers ties {crew_rate} an hour each. Give bars each way, ties, robot hours and crew hours.\n" + answer_keys_line(fields))
    return Task(f"rob-rebar-{i:04d}", "robotics", "rebar_tying", "Rebar-tying robot vs crew", "medium", prompt,
                {"bars_long_direction": n_long, "bars_short_direction": n_trans, "ties": ties,
                 "robot_hours": round(robot_h, 4), "crew_hours": round(crew_h, 4)}, fields)


def bricklaying(rng: random.Random, i: int) -> Task:
    length, height = rng.randint(80, 600), rng.choice([8, 10, 12, 14, 16])
    openings = rng.randint(0, 20) * rng.choice([15, 21, 24])
    per_sf = 6.86                                                # modular brick incl. mortar joint
    robot_bph, uptime, hrs = rng.choice([250, 300, 350]), rng.choice([60, 70, 80]), rng.choice([8, 10])
    mason_bpd, masons = rng.choice([450, 500, 550]), rng.choice([2, 3, 4])
    area = length * height - openings
    bricks = math.ceil(area * per_sf)
    robot_days = bricks / (robot_bph * uptime / 100 * hrs)
    crew_days = bricks / (mason_bpd * masons)
    fields = {"net_wall_area_sf": number(abs_tol=0.5), "bricks": INTEGER, "robot_days": number(0.003, 0.01), "crew_days": number(0.003, 0.01),
              "faster": TEXT}
    prompt = (f"A bricklaying robot and a mason crew are compared on a wall {length} ft long and {height} ft high with {openings} sq ft "
              f"of openings. Use {per_sf} modular bricks per sq ft of net wall, rounded up to a whole brick. The robot lays "
              f"{robot_bph} bricks per running hour, runs {uptime}% of a {hrs}-hour shift; the crew is {masons} masons at {mason_bpd} "
              "bricks per mason per day. Give net wall area, bricks, robot days, crew days, and which is faster (\"robot\" or \"crew\").\n"
              + answer_keys_line(fields))
    return Task(f"rob-brick-{i:04d}", "robotics", "bricklaying", "Bricklaying robot throughput", "easy", prompt,
                {"net_wall_area_sf": area, "bricks": bricks, "robot_days": round(robot_days, 4), "crew_days": round(crew_days, 4),
                 "faster": "robot" if robot_days < crew_days else "crew"}, fields)
