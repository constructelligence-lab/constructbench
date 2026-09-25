"""Architecture (code-driven design checks) and design & engineering (sizing calculations).

Architecture prompts state the governing rules — load factors, exit-count thresholds, riser limits — because
codes differ by edition and jurisdiction; the task measures applying them correctly, not recalling one book.
Engineering prompts use textbook formulas a design engineer would apply without being told, and give only
the project inputs and material properties.
"""
from __future__ import annotations

import math
import random

from ..task import Task, number, INTEGER, TEXT, answer_keys_line
from .common import pick, r2, round_to

LOAD_FACTORS = [("Assembly — unconcentrated (tables and chairs)", 15, "net"), ("Business areas", 150, "gross"),
                ("Classroom", 20, "net"), ("Mercantile — sales floor", 60, "gross"), ("Storage / mechanical", 300, "gross"),
                ("Exercise room", 50, "gross"), ("Kitchen, commercial", 200, "gross")]


def occupancy(rng: random.Random, i: int) -> Task:
    spaces = rng.sample(LOAD_FACTORS, rng.randint(3, 5))
    rows, total = [], 0
    for name, factor, basis in spaces:
        area = round_to(rng.uniform(300, 6_000), 10)
        load = math.ceil(area / factor)
        total += load
        rows.append((name, area, factor, basis, load))
    exits = 1 if total <= 49 else 2 if total <= 500 else 3 if total <= 1000 else 4
    width = total * 0.2
    table = "\n".join(f"| {n} | {a:,.0f} sq ft ({b}) | {f} sq ft per occupant |" for n, a, f, b, _ in rows)
    fields = {"total_occupant_load": INTEGER, "required_exits": INTEGER, "min_egress_width_in": number(abs_tol=0.05)}
    prompt = ("A single-story tenant fit-out has these spaces. The area given for each is the one its load factor applies "
              "to (net or gross, as marked).\n\n| Space | Area | Occupant load factor |\n|---|---|---|\n" + table + "\n\n"
              "Rules for this jurisdiction: occupant load of each space = its area ÷ its load factor, rounded UP per space; "
              "the floor's occupant load is the sum. Exits required: 1 for up to 49 occupants, 2 for 50–500, 3 for 501–1,000, "
              "4 above 1,000. Minimum total egress width at doors is 0.2 inch per occupant.\n"
              "Give the total occupant load, the number of exits required, and the minimum total egress width in inches.\n"
              + answer_keys_line(fields))
    return Task(f"arch-occ-{i:04d}", "architecture", "occupancy_egress", "Occupant load and egress", "medium", prompt,
                {"total_occupant_load": total, "required_exits": exits, "min_egress_width_in": round(width, 2)}, fields)


def stairs(rng: random.Random, i: int) -> Task:
    ftf = rng.randint(120, 186)                    # floor-to-floor, inches
    max_riser, tread = rng.choice([(7.0, 11.0), (7.75, 10.0)])
    n = math.ceil(ftf / max_riser)
    riser = ftf / n
    run = (n - 1) * tread
    fields = {"risers": INTEGER, "riser_height_in": number(abs_tol=0.01), "treads": INTEGER, "total_run_in": number(abs_tol=0.05)}
    prompt = (f"Lay out a straight-run stair between floors {ftf} inches apart (finished floor to finished floor). The code "
              f"allows a maximum riser of {max_riser} in, and you will use a {tread} in tread depth. Use the fewest risers "
              "that satisfy the maximum, all risers equal. Treads number one fewer than risers; total run is treads × tread depth.\n"
              + answer_keys_line(fields))
    return Task(f"arch-stair-{i:04d}", "architecture", "stairs", "Stair geometry", "easy", prompt,
                {"risers": n, "riser_height_in": round(riser, 3), "treads": n - 1, "total_run_in": r2(run)}, fields)


def zoning(rng: random.Random, i: int) -> Task:
    lot_w, lot_d = rng.randint(80, 300), rng.randint(100, 400)
    far = rng.choice([1.5, 2.0, 2.5, 3.0, 4.0, 6.0])
    # L-shaped footprint: a main block plus a wing.
    a, b = rng.randint(40, int(lot_w * .7)), rng.randint(40, int(lot_d * .6))
    c, d = rng.randint(15, 60), rng.randint(20, 80)
    footprint = a * b + c * d
    stories = rng.randint(2, 12)
    gfa = footprint * stories
    allowed = lot_w * lot_d * far
    fields = {"proposed_gross_floor_area": number(abs_tol=0.5), "max_allowed_floor_area": number(abs_tol=0.5),
              "complies": TEXT, "margin_sq_ft": number(abs_tol=0.5)}
    prompt = (f"A {lot_w} ft × {lot_d} ft lot is zoned with a maximum floor area ratio (FAR) of {far}. The proposed building "
              f"footprint is L-shaped: a {a} ft × {b} ft main block plus a separate, non-overlapping {c} ft × {d} ft wing. "
              f"Every one of its {stories} stories has that same footprint.\n"
              "Give the proposed gross floor area, the maximum floor area the FAR allows, whether it complies (\"yes\"/\"no\"), "
              "and the margin in sq ft (allowed − proposed; negative if over).\n" + answer_keys_line(fields))
    return Task(f"arch-far-{i:04d}", "architecture", "zoning", "Zoning floor area", "easy", prompt,
                {"proposed_gross_floor_area": gfa, "max_allowed_floor_area": r2(allowed), "complies": "yes" if gfa <= allowed else "no",
                 "margin_sq_ft": r2(allowed - gfa)}, fields)


def beam(rng: random.Random, i: int) -> Task:
    span = rng.randint(12, 36)                  # ft
    w = round_to(rng.uniform(300, 2_400), 25)    # plf, total uniform load
    fb = rng.choice([1_000, 1_350, 2_400, 24_000])  # psi (wood or steel allowable)
    e = 29_000_000 if fb == 24_000 else 1_600_000
    I = round_to(rng.uniform(150, 2_500), 5) if e < 2e7 else round_to(rng.uniform(80, 1_200), 5)
    m_ftlb = w * span ** 2 / 8
    v_lb = w * span / 2
    s_req = m_ftlb * 12 / fb
    defl = 5 * (w / 12) * (span * 12) ** 4 / (384 * e * I)
    limit = span * 12 / 360
    fields = {"max_moment_ft_kips": number(0.002), "max_shear_kips": number(0.002), "required_section_modulus_in3": number(0.003),
              "deflection_in": number(0.005), "deflection_ok_L360": TEXT}
    prompt = (f"A simply supported beam spans {span} ft and carries a total uniform load of {w:,.0f} lb/ft (self-weight included). "
              f"Allowable bending stress Fb = {fb:,} psi; E = {e:,} psi; the trial section has I = {I:g} in⁴.\n"
              "Give the maximum bending moment (ft-kips), the maximum shear (kips), the required section modulus in in³ "
              "(M ÷ Fb, with consistent units), the midspan deflection in inches under this load, and whether the deflection "
              "meets L/360 (\"yes\"/\"no\").\n" + answer_keys_line(fields))
    return Task(f"des-beam-{i:04d}", "design", "structural", "Beam bending, shear and deflection", "medium", prompt,
                {"max_moment_ft_kips": round(m_ftlb / 1000, 4), "max_shear_kips": round(v_lb / 1000, 4),
                 "required_section_modulus_in3": round(s_req, 3), "deflection_in": round(defl, 4),
                 "deflection_ok_L360": "yes" if defl <= limit else "no"}, fields)


def electrical(rng: random.Random, i: int) -> Task:
    kw = round(rng.uniform(15, 400), 1)
    volts = rng.choice([208, 480])
    pf = rng.choice([0.8, 0.85, 0.9, 0.95])
    amps = kw * 1000 / (math.sqrt(3) * volts * pf)
    sizes = [15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 110, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450, 500,
             600, 700, 800, 1000, 1200, 1600, 2000]
    need = amps * 1.25
    breaker = next(s for s in sizes if s >= need)
    fields = {"line_current_amps": number(0.003), "min_breaker_amps": INTEGER}
    prompt = (f"A continuous three-phase load draws {kw} kW at {volts} V with a power factor of {pf}.\n"
              "Give the line current, and the smallest standard breaker rating that is at least 125% of that current. "
              f"Standard ratings (A): {', '.join(map(str, sizes))}.\n" + answer_keys_line(fields))
    return Task(f"des-elec-{i:04d}", "design", "electrical", "Three-phase load and breaker", "easy", prompt,
                {"line_current_amps": round(amps, 3), "min_breaker_amps": breaker}, fields)


def duct(rng: random.Random, i: int) -> Task:
    cfm = round_to(rng.uniform(400, 12_000), 50)
    wdt, hgt = rng.choice([10, 12, 14, 16, 18, 20, 24, 30, 36]), rng.choice([6, 8, 10, 12, 14, 16, 18, 20])
    area = wdt * hgt / 144
    vel = cfm / area
    diam = math.sqrt(4 * area / math.pi) * 12
    fields = {"velocity_fpm": number(0.003), "equal_area_round_diameter_in": number(abs_tol=0.02)}
    prompt = (f"A supply duct carries {cfm:,.0f} CFM through a {wdt} in × {hgt} in rectangular section (inside dimensions).\n"
              "Give the air velocity in feet per minute, and the diameter of a round duct with the same cross-sectional area "
              "(equal area, not equal friction), in inches.\n" + answer_keys_line(fields))
    return Task(f"des-duct-{i:04d}", "design", "mechanical", "Duct velocity and equivalent round", "easy", prompt,
                {"velocity_fpm": round(vel, 2), "equal_area_round_diameter_in": round(diam, 3)}, fields)
