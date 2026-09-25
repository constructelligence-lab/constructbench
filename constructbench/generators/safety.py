"""Safety: incident rates, fall clearance, trench protection — and safety drawings rendered as images.

Rules are stated in each prompt (the task is applying them, not reciting a regulation). The rendered tasks are
measured off a scaled grid, the way a safety manager checks a drawing or a photo with a known reference.
"""
from __future__ import annotations

import math
import random

from ..task import Task, number, INTEGER, TEXT, answer_keys_line
from ..render import Canvas


def incident_rates(rng: random.Random, i: int) -> Task:
    hours = rng.randint(80_000, 2_400_000)
    recordable = rng.randint(1, 40)
    dart = rng.randint(0, recordable)
    lost = rng.randint(0, dart)
    f = 200_000 / hours
    fields = {"trir": number(abs_tol=0.005), "dart_rate": number(abs_tol=0.005), "ltir": number(abs_tol=0.005)}
    prompt = (f"A contractor's crews worked {hours:,} hours this year. There were {recordable} OSHA-recordable injuries; "
              f"{dart} of them involved days away, restricted duty or job transfer (DART), and {lost} involved days away from work.\n"
              "Using the standard 200,000-hour basis (100 full-time workers for a year), give the total recordable incident "
              "rate (TRIR), the DART rate and the lost-time incident rate (LTIR).\n" + answer_keys_line(fields))
    return Task(f"saf-rate-{i:04d}", "safety", "incident_rates", "Incident rates", "easy", prompt,
                {"trir": round(recordable * f, 4), "dart_rate": round(dart * f, 4), "ltir": round(lost * f, 4)}, fields)


def fall_clearance(rng: random.Random, i: int) -> Task:
    lanyard = rng.choice([4, 6])
    decel = 3.5
    d_ring = rng.choice([5.0, 5.5, 6.0])           # worker's D-ring height above feet
    sf = rng.choice([2.0, 3.0])
    anchor = rng.choice(["at foot level", "at D-ring height", "overhead, 2 ft above the D-ring"])
    offset = {"at foot level": d_ring, "at D-ring height": 0.0, "overhead, 2 ft above the D-ring": -2.0}[anchor]
    # Clearance below the working surface = free fall + deceleration + D-ring height + safety factor,
    # where free fall = lanyard length + how far the D-ring sits above the anchor (negative if below it).
    free_fall = max(0.0, lanyard + offset)
    required = free_fall + decel + d_ring + sf
    available = round(rng.uniform(required - 5, required + 6), 1)
    fields = {"free_fall_ft": number(abs_tol=0.01), "required_clearance_ft": number(abs_tol=0.01), "adequate": TEXT}
    prompt = (f"A worker uses a {lanyard} ft shock-absorbing lanyard tied off to an anchor {anchor}. The D-ring sits "
              f"{d_ring} ft above the worker's feet. The shock absorber deploys up to {decel} ft. Use a {sf} ft safety factor.\n"
              "Free fall = lanyard length + the distance the D-ring is above the anchor (negative when the anchor is higher; "
              "never below zero). Required clearance below the working surface = free fall + deceleration + D-ring height + "
              f"safety factor. There are {available} ft to the level below. Give the free fall distance, the required "
              "clearance, and whether the available clearance is adequate (\"yes\"/\"no\").\n" + answer_keys_line(fields))
    return Task(f"saf-fall-{i:04d}", "safety", "fall_clearance", "Fall clearance", "medium", prompt,
                {"free_fall_ft": free_fall, "required_clearance_ft": round(required, 2), "adequate": "yes" if available >= required else "no"},
                fields, {"anchor": anchor})


def trench(rng: random.Random, i: int) -> Task:
    depth = rng.choice([4, 6, 7, 8, 10, 12, 14, 16, 18])
    soil = rng.choice(["A", "B", "C"])
    ratio = {"A": 0.75, "B": 1.0, "C": 1.5}[soil]
    bottom = rng.choice([2, 3, 4, 6])
    top = bottom + 2 * ratio * depth
    needs = "yes" if depth >= 5 else "no"
    engineer = "yes" if depth > 20 else "no"
    fields = {"protective_system_required": TEXT, "top_width_ft": number(abs_tol=0.01), "slope_ratio_h_per_v": number(abs_tol=0.001)}
    prompt = (f"A trench will be dug {depth} ft deep with a {bottom} ft wide bottom in Type {soil} soil. Rules: a protective "
              "system is required at 5 ft deep or more (unless in stable rock); sloping both walls from the bottom edge is "
              "acceptable, at a maximum slope of 3/4 horizontal to 1 vertical for Type A, 1:1 for Type B and 1½:1 for Type C.\n"
              "Give whether a protective system is required (\"yes\"/\"no\"), the horizontal-to-vertical slope ratio for this soil, "
              "and the width at the top of the trench with both sides sloped at that maximum (even if not required).\n"
              + answer_keys_line(fields))
    return Task(f"saf-trench-{i:04d}", "safety", "excavation", "Trench protective system", "easy", prompt,
                {"protective_system_required": needs, "top_width_ft": round(top, 3), "slope_ratio_h_per_v": ratio}, fields,
                {"engineer_required": engineer})


# ── Rendered safety drawings ─────────────────────────────────────────────────────────────────────────────────

def ladder(rng: random.Random, i: int) -> Task:
    """A ladder elevation on a scaled grid: check the 4:1 rule and the 3 ft extension above the landing."""
    ft = 1                                   # one grid square = 1 ft
    cell = 26
    landing = rng.randint(8, 16)             # height of the upper landing, ft
    base = rng.choice([landing // 4 - 1, landing // 4, landing // 4 + 1, landing // 4 + 2])
    base = max(1, base)
    ext = rng.choice([1, 2, 3, 4])           # ft the rails extend above the landing
    top_h = landing + ext
    gw, gh = 12, top_h + 3
    m = 40
    cv = Canvas(m * 2 + gw * cell, m * 2 + gh * cell + 40)
    m_top = m + 20                           # room for a two-line title
    ox, oy = m, m_top + gh * cell            # ground line origin (left)
    for gx in range(gw + 1):
        cv.line(ox + gx * cell, m_top, ox + gx * cell, oy, v=225)
    for gy in range(gh + 1):
        cv.line(ox, oy - gy * cell, ox + gw * cell, oy - gy * cell, v=225)
    wall_x = ox + 9 * cell
    cv.line(ox, oy, ox + gw * cell, oy, t=4)                                  # ground
    cv.fill(wall_x, oy - landing * cell, ox + gw * cell, oy, v=170)           # building / landing
    cv.line(wall_x, oy - landing * cell, ox + gw * cell, oy - landing * cell, t=4)
    foot_x = wall_x - base * cell
    # Ladder rails: from the foot to the landing edge, then straight on past it by the extension.
    dx, dy = wall_x - foot_x, landing * cell
    top_x = wall_x + dx * ext / landing if landing else wall_x
    cv.line(foot_x, oy, int(top_x), oy - top_h * cell, t=5)
    cv.text(ox, 10, "LADDER ELEVATION", scale=2)
    cv.text(ox, 32, "1 GRID SQUARE = 1 FT", scale=2)
    working = landing                        # the 4:1 rule uses the height to the upper support point
    ok_ratio = abs(base - working / 4) <= 0.5
    fields = {"landing_height_ft": INTEGER, "base_offset_ft": INTEGER, "extension_above_landing_ft": INTEGER,
              "meets_4_to_1": TEXT, "meets_3ft_extension": TEXT}
    prompt = ("The attached image is a side elevation of a portable ladder set up to reach a landing, drawn on a grid (the "
              "scale is printed on the sheet). Read the landing height, the horizontal distance from the ladder's foot to the "
              "face of the building, and how far the rails extend above the landing (vertically).\n"
              "Rules: the base offset should be 1/4 of the height to the landing (within ½ ft counts as meeting it), and the "
              "rails must extend at least 3 ft above the landing. Answer \"yes\"/\"no\" for each rule.\n" + answer_keys_line(fields))
    return Task(f"saf-ladder-{i:04d}", "safety", "ladder_image", "Ladder setup from a drawing", "hard", prompt,
                {"landing_height_ft": landing, "base_offset_ft": base, "extension_above_landing_ft": ext,
                 "meets_4_to_1": "yes" if ok_ratio else "no", "meets_3ft_extension": "yes" if ext >= 3 else "no"},
                fields, {}, [cv.attachment(f"ladder-{i}.png")])


def crane_zone(rng: random.Random, i: int) -> Task:
    """A lift plan: count the workers standing inside the crane's swing radius."""
    w, h = 900, 640
    cv = Canvas(w, h)
    cv.rect(20, 20, w - 20, h - 20, t=3)
    cv.text(34, 32, "LIFT PLAN - SWING RADIUS", scale=2)
    cx, cy = rng.randint(330, 570), rng.randint(270, 380)
    r = rng.randint(150, 230)
    cv.fill(cx - 14, cy - 14, cx + 14, cy + 14)                 # crane
    cv.circle(cx, cy, r, v=0, t=3)                              # swing radius
    cv.text(cx - 40, cy + 24, "CRANE", scale=2)
    cv.circle(620, 44, 7, filled=True); cv.text(634, 38, "WORKER", scale=2)
    inside = outside = 0
    placed = []
    for _ in range(rng.randint(10, 26)):
        for _t in range(200):
            x, y = rng.randint(50, w - 50), rng.randint(80, h - 50)
            d = math.hypot(x - cx, y - cy)
            if abs(d - r) < 22 or d < 40 or any(math.hypot(x - a, y - b) < 28 for a, b in placed):
                continue                                         # keep workers clearly in or out
            placed.append((x, y))
            cv.circle(x, y, 7, filled=True)
            if d < r:
                inside += 1
            else:
                outside += 1
            break
    fields = {"workers_inside_swing_radius": INTEGER, "workers_total": INTEGER}
    prompt = ("The attached image is a lift plan. The heavy circle is the crane's swing radius around the crane (filled "
              "square); filled dots are workers (see the legend — the legend dot is not a worker). Count the workers inside "
              "the swing radius, and all workers on the plan.\n" + answer_keys_line(fields))
    return Task(f"saf-crane-{i:04d}", "safety", "crane_zone_image", "Workers inside a crane swing radius", "hard", prompt,
                {"workers_inside_swing_radius": inside, "workers_total": inside + outside}, fields, {},
                [cv.attachment(f"crane-{i}.png")])


def guardrail(rng: random.Random, i: int) -> Task:
    """A guardrail elevation on a 3-inch grid: measure top rail and midrail, check them."""
    unit = 3                                  # inches per grid square
    cell = 22
    top = rng.choice([13, 14, 15, 16])        # grid squares: 39, 42, 45, 48 in
    mid = rng.choice([6, 7, 8])               # 18, 21, 24 in
    toe = rng.choice([0, 1, 2])               # toeboard height in squares (0 = none)
    gw, gh = 24, 19
    m = 40
    cv = Canvas(m * 2 + gw * cell, m * 2 + gh * cell + 30)
    ox, oy = m, m + gh * cell
    for gx in range(gw + 1):
        cv.line(ox + gx * cell, m, ox + gx * cell, oy, v=225)
    for gy in range(gh + 1):
        cv.line(ox, oy - gy * cell, ox + gw * cell, oy - gy * cell, v=225)
    cv.line(ox, oy, ox + gw * cell, oy, t=5)                                   # walking surface
    for px in (3, 12, 21):
        cv.line(ox + px * cell, oy, ox + px * cell, oy - top * cell, t=5)      # posts
    cv.line(ox + 3 * cell, oy - top * cell, ox + 21 * cell, oy - top * cell, t=5)
    cv.line(ox + 3 * cell, oy - mid * cell, ox + 21 * cell, oy - mid * cell, t=3)
    if toe:
        cv.fill(ox + 3 * cell, oy - toe * cell, ox + 21 * cell, oy)
    cv.text(ox, 12, "GUARDRAIL ELEVATION  1 GRID SQUARE = 3 IN", scale=2)
    top_in, mid_in, toe_in = top * unit, mid * unit, toe * unit
    fields = {"top_rail_height_in": INTEGER, "midrail_height_in": INTEGER, "top_rail_compliant": TEXT, "toeboard_present": TEXT}
    prompt = ("The attached image is an elevation of a guardrail at an open edge, drawn on a grid (scale on the sheet). Heights "
              "are measured from the walking surface (the heavy bottom line) to the top of each rail. Give the top rail height "
              "and midrail height in inches, whether the top rail meets 42 in ± 3 in (\"yes\"/\"no\"), and whether a toeboard (a "
              "solid band along the walking surface) is present (\"yes\"/\"no\").\n" + answer_keys_line(fields))
    return Task(f"saf-rail-{i:04d}", "safety", "guardrail_image", "Guardrail heights from a drawing", "medium", prompt,
                {"top_rail_height_in": top_in, "midrail_height_in": mid_in,
                 "top_rail_compliant": "yes" if 39 <= top_in <= 45 else "no", "toeboard_present": "yes" if toe else "no"},
                fields, {"toeboard_in": toe_in}, [cv.attachment(f"guardrail-{i}.png")])
