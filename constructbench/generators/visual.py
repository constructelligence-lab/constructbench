"""Visual intelligence: read a drawing or chart from an image.

Three kinds, each rendered from the numbers its answer is computed from:
  - a floor plan on a scaled grid (room areas, the largest room),
  - a plan sheet of symbols (count sprinkler heads and columns — counting is where vision models slip),
  - a Gantt chart (which activity finishes last, what is running in a given week).
"""
from __future__ import annotations

import random

from ..task import Task, number, INTEGER, TEXT, SET, answer_keys_line
from ..render import Canvas


def floor_plan(rng: random.Random, i: int) -> Task:
    gw, gh = rng.randint(10, 16), rng.randint(8, 12)          # plan size in grid squares
    ft = rng.choice([2, 4, 5])                                 # feet per grid square
    cell = 36
    # Split the footprint into rooms by repeated guillotine cuts.
    rooms = [(0, 0, gw, gh)]
    while len(rooms) < rng.randint(4, 6):
        rooms.sort(key=lambda r: (r[2] - r[0]) * (r[3] - r[1]), reverse=True)
        x0, y0, x1, y1 = rooms.pop(0)
        if (x1 - x0) >= (y1 - y0) and x1 - x0 >= 4:
            c = rng.randint(x0 + 2, x1 - 2); rooms += [(x0, y0, c, y1), (c, y0, x1, y1)]
        elif y1 - y0 >= 4:
            c = rng.randint(y0 + 2, y1 - 2); rooms += [(x0, y0, x1, c), (x0, c, x1, y1)]
        else:
            rooms.append((x0, y0, x1, y1)); break
    rooms.sort(key=lambda r: (r[1], r[0]))
    labels = [chr(ord("A") + k) for k in range(len(rooms))]
    m, top = 50, 70
    cv = Canvas(m * 2 + gw * cell, top + m + gh * cell + 20)
    for gx in range(gw + 1):
        cv.line(m + gx * cell, top, m + gx * cell, top + gh * cell, v=215)
    for gy in range(gh + 1):
        cv.line(m, top + gy * cell, m + gw * cell, top + gy * cell, v=215)
    for (x0, y0, x1, y1), lab in zip(rooms, labels):
        cv.rect(m + x0 * cell, top + y0 * cell, m + x1 * cell, top + y1 * cell, v=0, t=4)
        cx, cy = m + (x0 + x1) * cell // 2, top + (y0 + y1) * cell // 2
        cv.text(cx - 7, cy - 10, lab, scale=3)
    cv.text(m, 18, f"SCALE: 1 GRID SQUARE = {ft} FT", scale=2)
    areas = {lab: (x1 - x0) * (y1 - y0) * ft * ft for (x0, y0, x1, y1), lab in zip(rooms, labels)}
    ask = rng.choice(labels)
    largest = max(areas, key=areas.get)
    if sorted(areas.values())[-1] == sorted(areas.values())[-2]:
        return floor_plan(rng, i)
    fields = {"room_area_sq_ft": number(abs_tol=0.5), "largest_room": TEXT, "total_area_sq_ft": number(abs_tol=0.5)}
    prompt = (f"The attached image is a floor plan drawn on a grid; the scale is printed on the sheet. Rooms are outlined in "
              f"heavy lines and labelled with letters. Give the area of room {ask} in square feet, the letter of the largest "
              "room, and the total area of all rooms.\n" + answer_keys_line(fields))
    return Task(f"vis-plan-{i:04d}", "visual_intelligence", "floor_plan", "Read areas off a scaled plan", "medium", prompt,
                {"room_area_sq_ft": areas[ask], "largest_room": largest, "total_area_sq_ft": sum(areas.values())}, fields,
                {"room": ask}, [cv.attachment(f"plan-{i}.png")])


def symbols(rng: random.Random, i: int) -> Task:
    w, h = 900, 620
    cv = Canvas(w, h)
    cv.rect(20, 20, w - 20, h - 20, t=3)
    cv.text(34, 32, "SPRINKLER PLAN - LEVEL 2", scale=2)
    # Legend
    cv.circle(600, 44, 8, t=2); cv.text(616, 38, "HEAD", scale=2)
    cv.fill(740, 36, 756, 52); cv.text(764, 38, "COLUMN", scale=2)
    placed: list[tuple[int, int]] = []

    def free(x: int, y: int, r: int) -> bool:
        return all((x - a) ** 2 + (y - b) ** 2 > (r + 26) ** 2 for a, b in placed)

    heads = cols = 0
    n_heads, n_cols = rng.randint(9, 34), rng.randint(3, 12)
    tries = 0
    while (heads < n_heads or cols < n_cols) and tries < 5000:
        tries += 1
        x, y = rng.randint(60, w - 60), rng.randint(90, h - 50)
        if not free(x, y, 10):
            continue
        if heads < n_heads and (cols >= n_cols or rng.random() < .7):
            cv.circle(x, y, 9, t=2); heads += 1
        else:
            cv.fill(x - 9, y - 9, x + 9, y + 9); cols += 1
        placed.append((x, y))
    # A few pipe runs as distractors.
    for _ in range(rng.randint(2, 5)):
        y = rng.randint(100, h - 60)
        cv.line(40, y, w - 40, y, v=120, t=2, dash=12)
    fields = {"sprinkler_heads": INTEGER, "columns": INTEGER}
    prompt = ("The attached image is a sprinkler plan. The legend shows the symbols: an open circle is a sprinkler head, a "
              "filled square is a structural column; dashed lines are pipe. Count every sprinkler head and every column on "
              "the sheet (the legend symbols do not count).\n" + answer_keys_line(fields))
    return Task(f"vis-count-{i:04d}", "visual_intelligence", "symbol_count", "Count symbols on a plan", "hard", prompt,
                {"sprinkler_heads": heads, "columns": cols}, fields, {}, [cv.attachment(f"symbols-{i}.png")])


def gantt(rng: random.Random, i: int) -> Task:
    names = ["MOBILIZE", "EXCAVATE", "FOUNDATIONS", "STEEL", "DECKS", "ROOFING", "ENVELOPE", "MEP ROUGH", "DRYWALL",
             "FINISHES", "COMMISSION"]
    n = rng.randint(6, 10)
    acts, start = [], 0
    for k in range(n):
        s = max(0, start + rng.randint(-2, 3))
        d = rng.randint(2, 8)
        acts.append((names[k], s, s + d))
        start = s + rng.randint(1, 3)
    weeks = max(e for _, _, e in acts) + 1
    ends = sorted(e for _, _, e in acts)
    if ends[-1] == ends[-2]:
        return gantt(rng, i)                      # one activity must finish last
    last = max(acts, key=lambda a: a[2])
    probe = rng.randint(2, weeks - 2)
    running = [a for a, s, e in acts if s <= probe < e]
    lw, cw, rh, top = 190, max(22, min(40, 820 // weeks)), 34, 80
    cv = Canvas(lw + weeks * cw + 40, top + n * rh + 40)
    cv.text(10, 14, "SCHEDULE - WEEKS", scale=2)
    for wk in range(weeks + 1):
        x = lw + wk * cw
        cv.line(x, top - 8, x, top + n * rh, v=200)
        if wk < weeks and wk % max(1, weeks // 12) == 0:
            cv.text(x + 2, top - 28, str(wk), scale=2)
    for r, (nm, s, e) in enumerate(acts):
        y = top + r * rh
        cv.text(10, y + 10, nm, scale=2)
        cv.fill(lw + s * cw + 1, y + 7, lw + e * cw, y + rh - 7, v=40)
    fields = {"finishes_last": TEXT, "finish_week": INTEGER, "running_in_week": SET}
    prompt = ("The attached image is a bar chart schedule. Columns are weeks, numbered from 0 at the left; a bar that starts at "
              "the left edge of week S and ends at the left edge of week E occupies weeks S through E−1, and the activity "
              f"finishes at week E. Name the activity that finishes last, give the week it finishes (E), and list every "
              f"activity in progress during week {probe}.\n" + answer_keys_line(fields))
    return Task(f"vis-gantt-{i:04d}", "visual_intelligence", "gantt", "Read a bar chart schedule", "medium", prompt,
                {"finishes_last": last[0], "finish_week": last[2], "running_in_week": running}, fields,
                {"probe_week": probe}, [cv.attachment(f"gantt-{i}.png")])
