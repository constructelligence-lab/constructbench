"""Preconstruction (bid leveling, the bid-day number), unit-rate estimating, and RFI log analysis."""
from __future__ import annotations

import datetime as dt
import random

from ..task import Task, number, INTEGER, TEXT, SET, answer_keys_line
from .common import VENDORS, money, pick, r2, round_to

SCOPE_ITEMS = ["Cleanup & dumpsters", "Firestopping", "Temporary protection", "Permits & inspections", "Bonds",
               "Hoisting", "Winter conditions", "Shop drawings & submittals", "Testing & balancing"]


def bid_leveling(rng: random.Random, i: int) -> Task:
    trade = pick(rng, ["Mechanical", "Electrical", "Drywall & framing", "Plumbing", "Fire protection", "Roofing"])
    items = rng.sample(SCOPE_ITEMS, rng.randint(3, 5))
    plug = {it: round_to(rng.uniform(2_000, 45_000), 500) for it in items}   # estimator's value for each item
    bidders = rng.sample(VENDORS, rng.randint(3, 4))
    rows, leveled = [], {}
    for b in bidders:
        base = round_to(rng.uniform(400_000, 2_400_000), 1_000)
        excl = sorted(rng.sample(items, rng.randint(0, len(items))))
        total = base + sum(plug[x] for x in excl)
        leveled[b] = total
        rows.append((b, base, excl))
    # Make the low base bid not the low leveled bid most of the time — that's the lesson of leveling.
    low_base = min(rows, key=lambda r: r[1])[0]
    low = min(leveled, key=leveled.get)
    if sorted(leveled.values())[0] == sorted(leveled.values())[1]:
        return bid_leveling(rng, i)                  # a tie has two right answers
    table = "\n".join(f"| {b} | {money(base)} | {', '.join(ex) or 'none'} |" for b, base, ex in rows)
    plugs = "\n".join(f"| {it} | {money(v)} |" for it, v in plug.items())
    fields = {"low_bidder_after_leveling": TEXT, "leveled_low_total": number(0, 0.5), "spread_high_minus_low": number(0, 0.5)}
    prompt = (f"Level these {trade} subcontractor bids. Every bidder must carry the full scope; where a bid excludes an item, "
              "add the estimator's value for it.\n\n| Bidder | Base bid | Exclusions |\n|---|---|---|\n" + table +
              "\n\n| Scope item | Estimator's value |\n|---|---|\n" + plugs + "\n\n"
              "Give the low bidder after leveling, its leveled total, and the spread between the highest and lowest leveled totals.\n"
              + answer_keys_line(fields))
    return Task(f"pre-lvl-{i:04d}", "preconstruction", "bid_leveling", "Bid leveling with scope gaps", "medium", prompt,
                {"low_bidder_after_leveling": low, "leveled_low_total": r2(leveled[low]),
                 "spread_high_minus_low": r2(max(leveled.values()) - leveled[low])}, fields, {"low_base_bidder": low_base})


def bid_day(rng: random.Random, i: int) -> Task:
    trades = rng.sample(["Sitework", "Concrete", "Masonry", "Steel", "Carpentry", "Roofing", "Glazing", "Drywall",
                         "Flooring", "Painting", "Fire protection", "Plumbing", "HVAC", "Electrical"], rng.randint(5, 9))
    lows = {t: round_to(rng.uniform(80_000, 2_200_000), 1_000) for t in trades}
    gc = round_to(rng.uniform(150_000, 900_000), 1_000)
    cont = rng.choice([2, 3, 5])
    fee = rng.choice([3, 4, 5, 6])
    ins = rng.choice([0.9, 1.1, 1.25])
    bond = rng.choice([0.7, 0.85, 1.0])
    cost = sum(lows.values()) + gc
    contingency = cost * cont / 100
    fee_amt = (cost + contingency) * fee / 100
    ins_amt = (cost + contingency + fee_amt) * ins / 100
    bond_amt = (cost + contingency + fee_amt + ins_amt) * bond / 100
    total = cost + contingency + fee_amt + ins_amt + bond_amt
    table = "\n".join(f"| {t} | {money(v)} |" for t, v in lows.items())
    fields = {"direct_cost": number(0, 1), "bid_total": number(0.0005, 1)}
    prompt = ("Assemble the bid-day number for a lump-sum general contract.\n\n| Trade (low leveled bid) | Amount |\n|---|---|\n"
              + table + f"\n\nGeneral conditions: {money(gc)}. Direct cost = trades + general conditions. Then add, in order, "
              f"each computed on the running total so far: contingency {cont}%, fee {fee}%, general liability insurance {ins}%, "
              f"and bond {bond}%.\nGive the direct cost and the bid total.\n" + answer_keys_line(fields))
    return Task(f"pre-bid-{i:04d}", "preconstruction", "bid_day", "Bid-day number", "easy", prompt,
                {"direct_cost": r2(cost), "bid_total": r2(total)}, fields)


def unit_estimate(rng: random.Random, i: int) -> Task:
    scope = pick(rng, [("gypsum board, hung and finished level 4", "SF", 0.018, 0.034, 0.62),
                       ("3/4 in EMT conduit with fittings", "LF", 0.07, 0.12, 2.35),
                       ("4 in slab on grade, placed and finished", "SF", 0.012, 0.022, 2.10),
                       ("12x8 galvanized rectangular duct", "LB", 0.09, 0.15, 1.85)])
    qty = round_to(rng.uniform(1_500, 60_000), 50)
    mh = round(rng.uniform(scope[2], scope[3]), 4)
    wage = rng.choice([62, 68, 74, 81, 88])
    mat_unit = round(scope[4] * rng.uniform(.9, 1.2), 2)
    waste = rng.choice([5, 8, 10])
    hours = qty * mh
    labor = hours * wage
    material = qty * (1 + waste / 100) * mat_unit
    total = labor + material
    fields = {"labor_hours": number(0.001, 0.1), "labor_cost": number(0.001, 1), "material_cost": number(0.001, 1),
              "total_cost": number(0.001, 1), "unit_cost_per_unit": number(0.002, 0.005)}
    prompt = (f"Estimate {qty:,.0f} {scope[1]} of {scope[0]}. Production: {mh} labor-hours per {scope[1]}. Loaded labor rate "
              f"${wage}/hour. Material ${mat_unit} per {scope[1]} plus {waste}% waste on material quantity.\n"
              f"Give labor hours, labor cost, material cost, total cost, and the all-in unit cost per {scope[1]} (total ÷ {qty:,.0f}).\n"
              + answer_keys_line(fields))
    return Task(f"est-unit-{i:04d}", "estimating", "unit_rate", "Unit-rate estimate", "easy", prompt,
                {"labor_hours": r2(hours), "labor_cost": r2(labor), "material_cost": r2(material), "total_cost": r2(total),
                 "unit_cost_per_unit": round(total / qty, 4)}, fields)


def rfi_log(rng: random.Random, i: int) -> Task:
    today = dt.date(2026, 9, 25)
    n = rng.randint(8, 14)
    rows, open_late, ball = [], [], {}
    for k in range(1, n + 1):
        sent = today - dt.timedelta(days=rng.randint(1, 60))
        answered = None if rng.random() < .55 else sent + dt.timedelta(days=rng.randint(1, 40))
        if answered and answered > today:
            answered = None
        who = pick(rng, ["Architect", "Structural engineer", "MEP engineer", "Owner"])
        rows.append((f"RFI-{k:03d}", sent, answered, who, rng.random() < .3))
        if answered is None:
            age = (today - sent).days
            ball[who] = ball.get(who, 0) + 1
            if age > 14:
                open_late.append(f"RFI-{k:03d}")
    # One unambiguous answer: at least one open RFI, and no tie for the most.
    if not ball or sum(1 for w in ball if ball[w] == max(ball.values())) > 1:
        return rfi_log(rng, i)
    most = max(ball, key=ball.get)
    fmt = lambda d: d.strftime("%m/%d/%Y") if d else "—"
    table = "\n".join(f"| {r[0]} | {fmt(r[1])} | {fmt(r[2])} | {r[3]} | {'yes' if r[4] else 'no'} |" for r in rows)
    fields = {"open_count": INTEGER, "open_over_14_days": SET, "most_open_with": TEXT}
    prompt = (f"Today is {today:%m/%d/%Y}. From this RFI log, count the open RFIs (no answer date), list the open RFIs that "
              "have been open more than 14 calendar days since they were sent, and name who has the most open RFIs (ball in "
              "court). The cost-impact column is irrelevant to these questions.\n\n| RFI | Sent | Answered | Ball in court | Cost impact |\n"
              "|---|---|---|---|---|\n" + table + "\n" + answer_keys_line(fields))
    return Task(f"pm-rfi-{i:04d}", "project_management", "rfi_log", "RFI log aging", "easy", prompt,
                {"open_count": sum(1 for r in rows if r[2] is None), "open_over_14_days": open_late, "most_open_with": most}, fields)
