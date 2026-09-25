"""The built world beyond the jobsite: civil & infrastructure, sustainability & energy, real estate & facilities.

Same rules as every family: the prompt states the method and constants, the answer is computed from the same
numbers, and each task has exactly one right answer.
"""
from __future__ import annotations

import math
import random

from ..task import Task, number, INTEGER, TEXT, LIST, answer_keys_line
from .common import pick, round_to


# ── Civil & infrastructure ───────────────────────────────────────────────────────────────────────────────

def earthwork(rng: random.Random, i: int) -> Task:
    """Grid method: each cell's depth is the mean of its four corners' (proposed − existing); cut and fill separately."""
    nx, ny = rng.randint(3, 5), rng.randint(3, 4)          # cells
    step = rng.choice([25, 50])                            # ft
    base = rng.uniform(100, 140)
    ex = [[round(base + rng.uniform(-3.5, 3.5), 1) for _ in range(nx + 1)] for _ in range(ny + 1)]
    pad = round(base + rng.uniform(-1.5, 1.5), 1)          # a flat building pad
    cut = fill = 0.0
    for r in range(ny):
        for c in range(nx):
            d = sum(pad - ex[rr][cc] for rr, cc in ((r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1))) / 4
            v = step * step * abs(d) / 27
            if d > 0:
                fill += v
            else:
                cut += v
    table = "\n".join("| " + " | ".join(f"{e:.1f}" for e in row) + " |" for row in ex)
    header = "| " + " | ".join(f"C{k}" for k in range(nx + 1)) + " |\n|" + "---|" * (nx + 1)
    fields = {"cut_cy": number(0.002, 1), "fill_cy": number(0.002, 1), "net_cy": number(0.005, 2), "import_or_export": TEXT}
    prompt = (f"A site is surveyed on a {step} ft grid; existing spot elevations (ft) at the grid corners are below (rows run "
              f"north to south). The whole area is graded to a flat pad at elevation {pad} ft.\n\n{header}\n{table}\n\n"
              "Use the grid method: for each grid cell, depth = the average of (pad − existing) at its four corners; a positive "
              "depth is fill, negative is cut; cell volume = cell area × |depth| ÷ 27 (cubic yards). Sum cut and fill separately. "
              "Give total cut, total fill, net (fill − cut) and whether the site must \"import\" or \"export\" soil to balance.\n"
              + answer_keys_line(fields))
    return Task(f"civ-earth-{i:04d}", "civil", "earthwork", "Earthwork cut and fill", "hard", prompt,
                {"cut_cy": round(cut, 2), "fill_cy": round(fill, 2), "net_cy": round(fill - cut, 2),
                 "import_or_export": "import" if fill > cut else "export"}, fields)


def gravity_pipe(rng: random.Random, i: int) -> Task:
    length = rng.randint(120, 600)
    up = round(rng.uniform(95, 110), 2)
    slope_pct = rng.choice([0.4, 0.5, 0.75, 1.0, 1.5, 2.0])
    down = round(up - length * slope_pct / 100, 2)
    dia_in = rng.choice([8, 10, 12, 15, 18, 24])
    n = rng.choice([0.012, 0.013, 0.015])
    design = round(rng.uniform(0.3, 9), 2)
    s = (up - down) / length
    d = dia_in / 12
    a = math.pi * d * d / 4
    r = d / 4
    q = 1.49 / n * a * r ** (2 / 3) * math.sqrt(s)
    fields = {"slope_percent": number(abs_tol=0.005), "full_flow_cfs": number(0.005), "adequate": TEXT}
    prompt = (f"A storm sewer runs {length} ft from an upstream invert of {up} ft to a downstream invert of {down} ft, in "
              f"{dia_in} in diameter pipe with Manning's n = {n}. Design flow is {design} cfs.\n"
              "Give the slope as a percent, the full-flow capacity from Manning's equation in US units "
              "(Q = 1.49/n × A × R^(2/3) × S^(1/2), with A the full area and R = D/4 for a full circular pipe), and whether "
              "capacity is at least the design flow (\"yes\"/\"no\").\n" + answer_keys_line(fields))
    return Task(f"civ-pipe-{i:04d}", "civil", "gravity_pipe", "Gravity pipe slope and capacity", "medium", prompt,
                {"slope_percent": round(s * 100, 4), "full_flow_cfs": round(q, 4), "adequate": "yes" if q >= design else "no"}, fields)


def paving(rng: random.Random, i: int) -> Task:
    area_sy = round_to(rng.uniform(800, 25_000), 10)
    lifts = rng.choice([(2.0, 1.5), (2.5, 1.5), (3.0, 2.0)])     # base, surface inches
    density = rng.choice([110, 112, 115])                          # lb per SY per inch
    waste = rng.choice([3, 5])
    tons_base = area_sy * lifts[0] * density / 2000
    tons_surf = area_sy * lifts[1] * density / 2000
    total = (tons_base + tons_surf) * (1 + waste / 100)
    fields = {"base_course_tons": number(0.002, 0.5), "surface_course_tons": number(0.002, 0.5), "total_tons_with_waste": number(0.002, 0.5)}
    prompt = (f"Pave {area_sy:,.0f} square yards with a {lifts[0]} in base course and a {lifts[1]} in surface course of hot-mix "
              f"asphalt. Use {density} lb per square yard per inch of compacted thickness and add {waste}% waste to the total. "
              "Give tons of base, tons of surface (before waste), and total tons including waste (2,000 lb per ton).\n"
              + answer_keys_line(fields))
    return Task(f"civ-pave-{i:04d}", "civil", "paving", "Asphalt paving tonnage", "easy", prompt,
                {"base_course_tons": round(tons_base, 3), "surface_course_tons": round(tons_surf, 3),
                 "total_tons_with_waste": round(total, 3)}, fields)


# ── Sustainability & energy ──────────────────────────────────────────────────────────────────────────────

CARBON = [("Ready-mix concrete, 4000 psi", "m³", 320), ("Reinforcing steel", "t", 1_200), ("Structural steel sections", "t", 1_550),
          ("Aluminium curtain wall framing", "t", 9_200), ("Gypsum board", "m²", 3.1), ("Mineral wool insulation", "m³", 45),
          ("Float glass", "t", 1_400), ("CLT timber panels", "m³", 160)]


def embodied_carbon(rng: random.Random, i: int) -> Task:
    items = rng.sample(CARBON, rng.randint(4, 6))
    qty = {name: round(rng.uniform(5, 3_000) if unit != "t" else rng.uniform(2, 600), 1) for name, unit, _ in items}
    gfa = rng.randint(2_000, 40_000)                  # m²
    tot = {name: qty[name] * f for name, _, f in items}
    total_t = sum(tot.values()) / 1000
    biggest = max(tot, key=tot.get)
    if sorted(tot.values())[-1] == sorted(tot.values())[-2]:
        return embodied_carbon(rng, i)
    swap = pick(rng, [n for n, _, _ in items])
    cut = rng.choice([20, 30, 40])
    saved = tot[swap] * cut / 100 / 1000
    table = "\n".join(f"| {n} | {qty[n]:,} {u} | {f:,} kgCO₂e per {u} |" for n, u, f in items)
    fields = {"total_tCO2e": number(0.002, 0.05), "kgCO2e_per_m2": number(0.003, 0.05), "largest_contributor": TEXT, "saving_tCO2e": number(0.003, 0.02)}
    prompt = (f"Embodied carbon (A1–A3) for a {gfa:,} m² building, from its material take-off and the project's chosen emission "
              "factors:\n\n| Material | Quantity | Factor |\n|---|---|---|\n" + table + "\n\n"
              f"Give the total in tonnes CO₂e, the intensity in kgCO₂e per m² of floor area, the material contributing most, and "
              f"the saving in tonnes if the factor for \"{swap}\" is reduced by {cut}% (quantity unchanged).\n" + answer_keys_line(fields))
    return Task(f"sus-carbon-{i:04d}", "sustainability", "embodied_carbon", "Embodied carbon of a take-off", "medium", prompt,
                {"total_tCO2e": round(total_t, 4), "kgCO2e_per_m2": round(total_t * 1000 / gfa, 4), "largest_contributor": biggest,
                 "saving_tCO2e": round(saved, 4)}, fields)


def eui(rng: random.Random, i: int) -> Task:
    sf = rng.randint(20_000, 400_000)
    kwh = round_to(sf * rng.uniform(8, 22), 100)
    therms = round_to(sf * rng.uniform(0.05, 0.6), 10)
    e_rate, g_rate = round(rng.uniform(0.10, 0.26), 3), round(rng.uniform(0.9, 1.8), 2)
    kbtu = kwh * 3.412 + therms * 100
    fields = {"site_eui_kbtu_per_sf": number(0.002, 0.05), "annual_energy_cost": number(0.001, 1), "cost_per_sf": number(0.002, 0.005)}
    prompt = (f"A {sf:,} sq ft office used {kwh:,.0f} kWh of electricity and {therms:,.0f} therms of natural gas last year. "
              f"Electricity costs ${e_rate}/kWh and gas ${g_rate}/therm. Using 3.412 kBtu per kWh and 100 kBtu per therm, give the "
              "site energy use intensity (kBtu per sq ft per year), the annual energy cost, and cost per sq ft.\n" + answer_keys_line(fields))
    return Task(f"sus-eui-{i:04d}", "sustainability", "energy_use", "Energy use intensity and cost", "easy", prompt,
                {"site_eui_kbtu_per_sf": round(kbtu / sf, 4), "annual_energy_cost": round(kwh * e_rate + therms * g_rate, 2),
                 "cost_per_sf": round((kwh * e_rate + therms * g_rate) / sf, 4)}, fields)


def solar(rng: random.Random, i: int) -> Task:
    roof = rng.randint(4_000, 60_000)                      # usable sq ft
    usable = rng.choice([55, 60, 65, 70])
    panel_w, panel_sf = rng.choice([(400, 21.5), (430, 22.3), (450, 23.0)])
    yield_ = rng.choice([1_150, 1_300, 1_450, 1_600])      # kWh per kW-DC per year
    cost_w = round(rng.uniform(1.9, 3.1), 2)
    rate = round(rng.uniform(0.11, 0.28), 3)
    incentive = rng.choice([0, 30])
    panels = math.floor(roof * usable / 100 / panel_sf)
    kw = panels * panel_w / 1000
    kwh = kw * yield_
    net_cost = kw * 1000 * cost_w * (1 - incentive / 100)
    payback = net_cost / (kwh * rate)
    fields = {"panels": INTEGER, "system_kw_dc": number(abs_tol=0.01), "annual_kwh": number(0.001, 1), "simple_payback_years": number(0.003, 0.01)}
    prompt = (f"A {roof:,} sq ft roof has {usable}% of its area usable for PV. Modules are {panel_w} W, {panel_sf} sq ft each "
              "(whole modules only, round down). The site produces "
              f"{yield_:,} kWh per kW-DC per year. Installed cost is ${cost_w}/W-DC before a {incentive}% incentive, and the "
              f"building pays ${rate}/kWh. Give the number of modules, system size in kW-DC, annual kWh, and simple payback in years "
              "(net cost ÷ annual savings).\n" + answer_keys_line(fields))
    return Task(f"sus-pv-{i:04d}", "sustainability", "solar_pv", "Rooftop solar sizing and payback", "medium", prompt,
                {"panels": panels, "system_kw_dc": round(kw, 3), "annual_kwh": round(kwh, 2), "simple_payback_years": round(payback, 4)}, fields)


# ── Real estate & facilities ─────────────────────────────────────────────────────────────────────────────

def pro_forma(rng: random.Random, i: int) -> Task:
    units = rng.randint(24, 320)
    land = round_to(rng.uniform(1.5e6, 25e6), 50_000)
    hard_per_unit = round_to(rng.uniform(180_000, 380_000), 1_000)
    soft_pct = rng.choice([18, 22, 25, 28])
    rent = round_to(rng.uniform(1_600, 4_200), 25)
    vacancy = rng.choice([5, 6, 7])
    opex_pct = rng.choice([32, 35, 38, 40])
    cap = rng.choice([4.75, 5.0, 5.25, 5.5, 6.0])
    hard = units * hard_per_unit
    soft = hard * soft_pct / 100
    cost = land + hard + soft
    gpr = units * rent * 12
    egi = gpr * (1 - vacancy / 100)
    noi = egi * (1 - opex_pct / 100)
    yoc = noi / cost
    value = noi / (cap / 100)
    margin = (value - cost) / cost
    fields = {"total_development_cost": number(0.001, 100), "noi": number(0.001, 10), "yield_on_cost_pct": number(abs_tol=0.01),
              "stabilized_value": number(0.001, 100), "profit_margin_pct": number(abs_tol=0.05)}
    prompt = (f"A {units}-unit apartment development: land {money_(land)}, hard costs {money_(hard_per_unit)} per unit, soft costs "
              f"{soft_pct}% of hard costs. Stabilized rent averages {money_(rent)} per unit per month, vacancy and credit loss "
              f"{vacancy}% of gross potential rent, operating expenses {opex_pct}% of effective gross income. Exit cap rate {cap}%.\n"
              "Give total development cost, net operating income (NOI), yield on cost (NOI ÷ total cost, as a percent), stabilized "
              "value (NOI ÷ cap rate), and profit margin ((value − cost) ÷ cost, as a percent).\n" + answer_keys_line(fields))
    return Task(f"re-proforma-{i:04d}", "real_estate", "pro_forma", "Development pro forma", "medium", prompt,
                {"total_development_cost": round(cost, 2), "noi": round(noi, 2), "yield_on_cost_pct": round(yoc * 100, 4),
                 "stabilized_value": round(value, 2), "profit_margin_pct": round(margin * 100, 4)}, fields)


def money_(v: float) -> str:
    return f"${v:,.0f}"


def lifecycle(rng: random.Random, i: int) -> Task:
    years = rng.choice([15, 20, 25])
    rate = rng.choice([3, 4, 5, 6, 7])
    a_cap, b_cap = round_to(rng.uniform(150_000, 600_000), 1_000), None
    b_cap = round_to(a_cap * rng.uniform(1.15, 1.6), 1_000)
    a_op, b_op = round_to(rng.uniform(25_000, 90_000), 500), None
    b_op = round_to(a_op * rng.uniform(0.55, 0.9), 500)
    annuity = (1 - (1 + rate / 100) ** -years) / (rate / 100)
    npv_a = a_cap + a_op * annuity
    npv_b = b_cap + b_op * annuity
    better = "B" if npv_b < npv_a else "A"
    if abs(npv_a - npv_b) < 500:
        return lifecycle(rng, i)
    kind = pick(rng, ["chiller plant", "rooftop units", "boiler", "LED lighting retrofit", "elevator modernization"])
    fields = {"present_value_cost_a": number(0.001, 50), "present_value_cost_b": number(0.001, 50), "lower_lifecycle_cost": TEXT}
    prompt = (f"Compare two options for a {kind} over {years} years at a {rate}% real discount rate. Option A: {money_(a_cap)} "
              f"installed, {money_(a_op)} per year to run and maintain. Option B: {money_(b_cap)} installed, {money_(b_op)} per year. "
              "Annual costs are paid at the end of each year; no salvage value. Give the present value of each option's total cost "
              "and which has the lower lifecycle cost (\"A\" or \"B\").\n" + answer_keys_line(fields))
    return Task(f"re-lcc-{i:04d}", "real_estate", "lifecycle_cost", "Lifecycle cost (NPV) of two options", "medium", prompt,
                {"present_value_cost_a": round(npv_a, 2), "present_value_cost_b": round(npv_b, 2), "lower_lifecycle_cost": better}, fields)


def maintenance(rng: random.Random, i: int) -> Task:
    """Rank a facilities backlog by a stated risk score."""
    assets = rng.sample(["AHU-1", "AHU-2", "Chiller CH-1", "Boiler B-1", "Fire pump", "Elevator 2", "Roof section C",
                         "Switchgear MDP", "Cooling tower CT-1", "Domestic water heater", "Generator G-1", "Parking deck joints"], rng.randint(6, 9))
    rows, score = [], {}
    for a in assets:
        cond, crit, age = rng.randint(1, 5), rng.randint(1, 5), rng.randint(2, 40)
        life = rng.choice([15, 20, 25, 30])
        remaining = max(0, life - age)
        s = (6 - cond) * crit + (5 if remaining == 0 else 0)
        rows.append((a, cond, crit, age, life))
        score[a] = s
    ranked = sorted(score, key=lambda k: (-score[k], k))
    top3 = ranked[:3]
    if len(ranked) > 3 and score[ranked[2]] == score[ranked[3]]:
        return maintenance(rng, i)
    table = "\n".join(f"| {a} | {c} | {k} | {g} | {l} |" for a, c, k, g, l in rows)
    fields = {"top_priority": TEXT, "top_three": LIST, "top_score": INTEGER}
    prompt = ("Prioritize this facilities maintenance backlog. Condition is 1 (failed) to 5 (like new); criticality is 1 (low) to 5 "
              "(life safety). Risk score = (6 − condition) × criticality, plus 5 if the asset has reached or passed its expected "
              "life (age ≥ life). Ties break alphabetically.\n\n| Asset | Condition | Criticality | Age (yr) | Expected life (yr) |\n"
              "|---|---|---|---|---|\n" + table + "\n\nGive the top-priority asset, the top three in order as one comma-separated "
              "string, and the top score.\n" + answer_keys_line(fields))
    return Task(f"re-maint-{i:04d}", "real_estate", "maintenance_priority", "Maintenance backlog priority", "easy", prompt,
                {"top_priority": ranked[0], "top_three": top3, "top_score": score[ranked[0]]}, fields)
