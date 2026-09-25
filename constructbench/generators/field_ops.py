"""Field and project controls: G703 checking, critical path, labor productivity, cash flow, quantities."""
from __future__ import annotations

import math
import random

from ..task import Task, number, INTEGER, TEXT, SET, LIST, answer_keys_line
from .common import JOB_NAMES, job_no, money, pick, r2, round_to

G703_LINES = ["General conditions", "Sitework & foundations", "Concrete", "Structural steel", "Framing & rough carpentry",
              "Roofing", "Windows & glazing", "Mechanical", "Plumbing", "Electrical", "Drywall & finishes", "Change orders (approved)"]


def g703(rng: random.Random, i: int) -> Task:
    """A continuation sheet with planted arithmetic errors; find them and give the corrected total."""
    n = rng.randint(7, 11)
    lines = rng.sample(G703_LINES, n)
    rows = []
    for k, desc in enumerate(lines, 1):
        c = round_to(rng.uniform(80_000, 900_000), 1_000)
        d = round_to(c * rng.uniform(0, .7), 500)
        e = round_to(max(0, c - d) * rng.uniform(0, .35), 500)
        f = round_to(rng.uniform(0, 40_000), 500) if rng.random() < .25 else 0
        f = min(f, max(0, c - d - e))
        g = d + e + f
        rows.append([k, desc, c, d, e, f, g, c - g])
    n_err = rng.choice([1, 1, 2])
    bad = sorted(rng.sample(range(n), n_err))
    for b in bad:
        col = rng.choice([6, 7])                       # G wrong, or H wrong
        delta = round_to(rng.uniform(1_500, 25_000), 500) * rng.choice([1, -1])
        rows[b][col] += delta
    correct_total_g = sum(r[3] + r[4] + r[5] for r in rows)
    body = "\n".join(f"| {r[0]} | {r[1]} | {money(r[2])} | {money(r[3])} | {money(r[4])} | {money(r[5])} | {money(r[6])} | {money(r[7])} |" for r in rows)
    fields = {"error_lines": SET, "corrected_total_completed": number(0.0005, 1)}
    prompt = ("Check this AIA G703 continuation sheet before it goes to the owner. On a correct line, "
              "G (completed and stored to date) = D + E + F and H (balance to finish) = C − G.\n\n"
              "| Item | Description | C Scheduled value | D From previous | E This period | F Materials stored | G Completed & stored | H Balance to finish |\n"
              "|---|---|---|---|---|---|---|---|\n" + body + "\n\n"
              "List the item numbers of every line with an arithmetic error, and give the correct total of column G "
              "(recomputed as D + E + F on every line).\n" + answer_keys_line(fields))
    return Task(f"g703-{i:04d}", "document_recognition", "pay_applications", "Find the errors on a G703", "medium", prompt,
                {"error_lines": [str(rows[b][0]) for b in bad], "corrected_total_completed": r2(correct_total_g)}, fields)


def cpm(rng: random.Random, i: int) -> Task:
    """Critical path: project duration and the critical activities, finish-to-start logic."""
    n = rng.randint(7, 11)
    ids = [chr(ord("A") + k) for k in range(n)]
    names = ["Mobilize", "Excavate", "Footings", "Foundation walls", "Underground MEP", "Slab on grade", "Steel erection",
             "Deck & pour", "Roofing", "Exterior envelope", "MEP rough-in", "Framing", "Drywall", "Finishes", "Commissioning"]
    dur = {a: rng.randint(2, 15) for a in ids}
    preds = {ids[0]: []}
    for k in range(1, n):
        cands = ids[max(0, k - 3):k]
        m = 1 if k < 2 else rng.choice([1, 1, 2])
        preds[ids[k]] = sorted(rng.sample(cands, min(m, len(cands))))
    # Every activity except the last feeds something, so the network has one end.
    fed = {p for ps in preds.values() for p in ps}
    for a in ids[:-1]:
        if a not in fed:
            preds[ids[-1]] = sorted(set(preds[ids[-1]]) | {a})
    es, ef = {}, {}
    for a in ids:
        es[a] = max((ef[p] for p in preds[a]), default=0)
        ef[a] = es[a] + dur[a]
    project = max(ef.values())
    succ = {a: [b for b in ids if a in preds[b]] for a in ids}
    lf, ls = {}, {}
    for a in reversed(ids):
        lf[a] = min((ls[s] for s in succ[a]), default=project)
        ls[a] = lf[a] - dur[a]
    critical = [a for a in ids if ls[a] - es[a] == 0]
    table = "\n".join(f"| {a} | {names[k % len(names)]} | {dur[a]} | {', '.join(preds[a]) or '—'} |" for k, a in enumerate(ids))
    fields = {"project_duration_days": INTEGER, "critical_activities": SET}
    prompt = ("Schedule network for a building job. Durations are working days; all logic is finish-to-start with no "
              "lags, and the project starts on day 0.\n\n| ID | Activity | Duration | Predecessors |\n|---|---|---|---|\n"
              + table + "\n\nGive the project duration and the IDs of every activity with zero total float.\n"
              + answer_keys_line(fields))
    return Task(f"cpm-{i:04d}", "project_management", "scheduling", "Critical path", "hard", prompt,
                {"project_duration_days": project, "critical_activities": critical}, fields)


def labor(rng: random.Random, i: int) -> Task:
    budget_hrs = round_to(rng.uniform(800, 9_000), 10)
    pct = rng.randint(20, 80)
    pf = rng.uniform(0.85, 1.35)
    earned = budget_hrs * pct / 100
    actual = round(earned * pf)
    pf_calc = actual / earned
    forecast = budget_hrs * pf_calc
    rate = rng.choice([68, 74, 78, 86, 92, 104])
    cost_var = (forecast - budget_hrs) * rate
    code = pick(rng, ["Branch wiring", "Drywall hang & tape", "Concrete forming", "Pipe rough-in", "Framing", "Duct install"])
    fields = {"earned_hours": number(0.001, 0.5), "productivity_factor": number(abs_tol=0.005),
              "forecast_hours_at_completion": number(0.002, 1), "labor_cost_variance": number(0.003, 50)}
    prompt = (f"Cost code \"{code}\" on job {job_no(rng)} was budgeted at {budget_hrs:,.0f} labor hours. The field reports "
              f"{pct}% of the quantities installed, and payroll shows {actual:,} hours charged to the code so far.\n\n"
              "Earned hours are budget hours × percent installed. The productivity factor is actual hours ÷ earned hours "
              "(above 1.0 is worse than plan). Assume the rest of the code runs at the same productivity factor, so forecast "
              f"hours at completion = budget hours × productivity factor. The loaded labor rate is ${rate}/hour; give the "
              "labor cost variance at completion as (forecast hours − budget hours) × rate (positive is an overrun).\n"
              + answer_keys_line(fields))
    return Task(f"lab-{i:04d}", "project_management", "labor", "Labor productivity forecast", "easy", prompt,
                {"earned_hours": r2(earned), "productivity_factor": round(pf_calc, 4),
                 "forecast_hours_at_completion": r2(forecast), "labor_cost_variance": r2(cost_var)}, fields)


def cash(rng: random.Random, i: int) -> Task:
    weeks = rng.randint(8, 13)
    opening = round_to(rng.uniform(0.4e6, 2.5e6), 10_000)
    payroll = round_to(rng.uniform(90_000, 260_000), 5_000)
    rows, bal, low, low_w = [], opening, None, None
    for w in range(1, weeks + 1):
        cin = round_to(rng.uniform(250_000, 900_000), 5_000) if rng.random() < .45 else 0
        out = payroll + (round_to(rng.uniform(150_000, 520_000), 5_000) if w % 4 == 0 else 0) + round_to(rng.uniform(15_000, 80_000), 1_000)
        bal = bal + cin - out
        rows.append((w, cin, out))
        if low is None or bal < low:
            low, low_w = bal, w
    table = "\n".join(f"| {w} | {money(ci) if ci else '—'} | {money(o)} |" for w, ci, o in rows)
    fields = {"lowest_closing_balance": number(0.0005, 1), "lowest_week": INTEGER, "closing_balance_final_week": number(0.0005, 1)}
    prompt = (f"A contractor starts week 1 with {money(opening)} in the bank. The 13-week cash forecast lists receipts and "
              "disbursements by week (receipts already net of retainage):\n\n| Week | Cash in | Cash out |\n|---|---|---|\n"
              + table + "\n\nClosing balance = opening + cash in − cash out, carried week to week. Give the lowest closing "
              "balance, the week it occurs (the first such week if tied), and the closing balance in the last week listed.\n"
              + answer_keys_line(fields))
    return Task(f"cash-{i:04d}", "finance", "cash_flow", "Cash flow low point", "easy", prompt,
                {"lowest_closing_balance": r2(low), "lowest_week": low_w, "closing_balance_final_week": r2(bal)}, fields)


def quantities(rng: random.Random, i: int) -> Task:
    kind = rng.choice(["slab", "roof", "drywall"])
    if kind == "slab":
        l, w = rng.randint(40, 220), rng.randint(30, 160)
        t = rng.choice([4, 5, 6, 8])
        waste = rng.choice([5, 8, 10])
        cy = l * w * (t / 12) / 27 * (1 + waste / 100)
        order = math.ceil(cy * 2) / 2
        fields = {"cubic_yards_with_waste": number(0.002, 0.05), "order_quantity_cy": number(abs_tol=0.001)}
        prompt = (f"A slab on grade measures {l} ft × {w} ft and is {t} inches thick. Allow {waste}% waste. Give the "
                  "concrete volume in cubic yards including waste, and the quantity to order rounded up to the next half "
                  "cubic yard.\n" + answer_keys_line(fields))
        ans = {"cubic_yards_with_waste": round(cy, 3), "order_quantity_cy": order}
    elif kind == "roof":
        plan = rng.randint(1_800, 24_000)
        pitch = rng.choice([(4, 1.054), (6, 1.118), (8, 1.202), (10, 1.302), (12, 1.414)])
        waste = rng.choice([10, 12, 15])
        sq = plan * pitch[1] / 100 * (1 + waste / 100)
        bundles = math.ceil(sq * 3)
        fields = {"squares_with_waste": number(0.002, 0.05), "bundles": INTEGER}
        prompt = (f"A gable roof covers {plan:,} sq ft in plan. The pitch is {pitch[0]}/12, whose slope factor is {pitch[1]}. "
                  f"Add {waste}% waste. Shingles come 3 bundles to a square. Give the squares to buy (one square = 100 sq ft of "
                  "roof surface, including waste, not rounded) and the number of bundles, rounded up.\n" + answer_keys_line(fields))
        ans = {"squares_with_waste": round(sq, 3), "bundles": bundles}
    else:
        perim = rng.randint(120, 900)
        h = rng.choice([8, 9, 10, 12])
        doors, windows = rng.randint(2, 18), rng.randint(0, 24)
        waste = rng.choice([8, 10, 12])
        net = perim * h - doors * 21 - windows * 15
        sheets = math.ceil(net * (1 + waste / 100) / 32)
        fields = {"net_wall_area_sq_ft": number(abs_tol=0.5), "sheets_4x8": INTEGER}
        prompt = (f"Rooms total {perim} linear ft of wall, {h} ft high, one layer of board on one side. Deduct {doors} doors "
                  f"at 21 sq ft each and {windows} windows at 15 sq ft each. Add {waste}% waste. Give the net wall area and "
                  "the number of 4×8 sheets (32 sq ft each) to order, rounded up after adding waste.\n" + answer_keys_line(fields))
        ans = {"net_wall_area_sq_ft": net, "sheets_4x8": sheets}
    return Task(f"qty-{i:04d}", "estimating", "quantities", f"Quantity takeoff — {kind}", "easy", prompt, ans, fields, {"kind": kind})
