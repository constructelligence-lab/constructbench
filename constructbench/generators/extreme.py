"""Extreme tier: several documents or rule layers that interact, at a size where a slip anywhere spoils the answer.

Built after the expert tier saturated for Claude 5.5 models (study notebook, 2026-10-14). Same contract as every
family: all conventions stated, every answer computed here from the numbers the prompt prints, ambiguous draws
redrawn from the same rng (seeds rebuild byte for byte), and tests/test_extreme.py re-derives each answer from the
prompt text with separately written code.
"""
from __future__ import annotations

import datetime as dt
import math
import random

from ..task import Task, number, INTEGER, TEXT, SET, answer_keys_line
from .common import JOB_NAMES, VENDORS, job_no, money, pick, round_to
from .expert import CODES, Retry, _retrying

EXTREME = "extreme"


# ---------------------------------------------------------------- contracts: change-order log reconciliation

CO_WORK = ["Added roof drains", "Revised storefront at grid C", "Owner-requested electrical outlets", "Unforeseen rock",
           "Upgraded lobby finishes", "Additional fire dampers", "Relocated transformer pad", "Structural repair at L2",
           "Added data drops", "Revised stair handrails", "Extra waterproofing at elevator pit", "Generator upsizing",
           "Added acoustic insulation", "Revised casework layout", "Sidewalk replacement", "Additional site lighting"]


@_retrying
def co_reconciliation(rng: random.Random, i: int) -> Task:
    original = round_to(rng.uniform(4_000_000, 25_000_000), 1_000)
    n = rng.randint(10, 14)
    log, latest = [], {}
    for k in range(n):
        co = f"CO-{k + 1:02d}"
        revs = rng.choices([1, 2, 3], weights=[5, 3, 1])[0]
        amt = round_to(rng.uniform(4_000, 160_000), 50) * (1 if rng.random() > .1 else -1)
        for r in range(revs):
            final = r == revs - 1
            status = rng.choices(["Approved", "Pending", "Rejected"], weights=[6, 3, 1])[0] if final else "Superseded"
            log.append((co, r, CO_WORK[k % len(CO_WORK)], status, amt))
            if final:
                latest[co] = (status, amt)
            amt = round_to(amt * rng.uniform(0.7, 1.35), 50)
    # an approved owner directive priced from T&M tickets
    labor = {"Carpenter": 92.0, "Laborer": 68.0, "Electrician": 118.0, "Operator": 105.0}
    tickets = []
    for k in range(rng.randint(5, 9)):
        trade = pick(rng, list(labor))
        tickets.append((f"T-{301 + k}", trade, rng.choice([2, 4, 6, 8, 10, 12, 16]), round(rng.uniform(0, 3_500), 2)))
    od = sum(h * labor[t] for _, t, h, _ in tickets) + sum(m for *_, m in tickets) * 1.15
    od = round(od, 2)
    rng.shuffle(log)
    approved = {co: a for co, (s, a) in latest.items() if s == "Approved"}
    approved["OD-01"] = od
    pending = sum(a for s, a in latest.values() if s == "Pending")
    billing, over_cos, over_amt = {}, [], 0.0
    for co in sorted(latest) + ["OD-01"]:
        val = approved.get(co, 0.0)
        base = val if val > 0 else abs(latest.get(co, ("", 10_000))[1])
        r = rng.random()
        if r < .15:
            billed = round_to(base * rng.uniform(1.05, 1.4), 50)       # billed more than the value
        elif r < .25 and co not in approved:
            billed = round_to(base * rng.uniform(0.3, 1.0), 50)        # billed on a CO that is not approved
        else:
            billed = round_to(max(0.0, val) * rng.uniform(0, 1), 50) if val > 0 else 0.0
        billing[co] = billed
        allowed = max(0.0, val)
        if billed > allowed + 1e-9:
            over_cos.append(co); over_amt += billed - allowed
    if not over_cos or len(over_cos) == len(billing):
        raise Retry
    revised = original + sum(approved.values())
    logrows = "\n".join(f"| {co} | R{r} | {w} | {s} | {money(a)} |" for co, r, w, s, a in log)
    trows = "\n".join(f"| {tid} | {t} | {h} | {money(m, cents=True)} |" for tid, t, h, m in tickets)
    brows = "\n".join(f"| {co} | {money(b)} |" for co, b in billing.items() if b or rng.random() < .5)
    billing_shown = {r.split(" | ")[0].strip("| ") for r in brows.splitlines()}
    over_cos = [c for c in over_cos if c in billing_shown]
    over_amt = sum(billing[c] - max(0.0, approved.get(c, 0.0)) for c in over_cos)
    if not over_cos:
        raise Retry
    fields = {"revised_contract_sum": number(0.0005), "approved_changes_total": number(0.0005),
              "pending_exposure": number(0.0005), "overbilled_changes": SET, "overbilled_amount": number(0.001)}
    prompt = (
        f"Reconcile the change orders on {pick(rng, JOB_NAMES)}. Original contract sum: {money(original)}.\n\n"
        "Change-order log (rows are in no particular order; R0, R1, R2 are revisions; negative amounts are credits):\n\n"
        "| CO | Rev | Description | Status | Amount |\n|---|---|---|---|---|\n" + logrows + "\n\n"
        "Owner directive OD-01 (approved, to be priced on time and materials): value = the sum over the tickets of "
        "hours × the labor rate + materials × 1.15 (15% markup on materials only). Labor rates per hour: "
        + ", ".join(f"{t} ${r:.2f}" for t, r in labor.items()) + ".\n\n"
        "| Ticket | Trade | Hours | Materials |\n|---|---|---|---|\n" + trows + "\n\n"
        "Billed to date on change items in the current pay application (items not listed have billed $0):\n\n"
        "| Change item | Billed to date |\n|---|---|\n" + brows + "\n\n"
        "Rules: only the highest revision of each CO counts and its status decides; Superseded rows never count. The "
        "revised contract sum = original + approved COs + OD-01. Pending exposure = the sum of COs whose latest status is "
        "Pending. A change item is over-billed when billed to date exceeds its approved value (an item that is not approved, "
        "or a credit, has an approved value of $0 for this test); over-billed amount = total of (billed − approved value) "
        "over those items.\n\nGive the revised contract sum, the total of approved changes (COs + OD-01), the pending "
        "exposure, the over-billed change items (as written, e.g. \"CO-04\"), and the over-billed amount.\n"
        + answer_keys_line(fields))
    return Task(f"z-cos-{i:04d}", "contracts", "co_reconciliation", "Change-order log reconciliation", EXTREME, prompt,
                {"revised_contract_sum": round(revised, 2), "approved_changes_total": round(sum(approved.values()), 2),
                 "pending_exposure": round(pending, 2), "overbilled_changes": sorted(over_cos),
                 "overbilled_amount": round(over_amt, 2)}, fields, {"log_rows": len(log)})


# ---------------------------------------------------------------- estimating: finish takeoff through addenda

def ft_in(inches: int) -> str:
    return f"{inches // 12}'-{inches % 12}\""


PRODUCTS = {"CPT-1": ("carpet tile", "box", 48.0, 0.05, 212.40), "VCT-1": ("vinyl composition tile", "carton", 45.0, 0.07, 61.75),
            "PT-1": ("porcelain tile", "carton", 15.5, 0.10, 58.20), "LVT-1": ("luxury vinyl tile", "carton", 23.6, 0.06, 94.10)}
ROOMS = ["Office", "Open office", "Conference", "Corridor", "Break room", "Toilet", "Storage", "Reception", "Copy room",
         "Training", "Huddle", "Mothers room", "IT closet", "Wellness", "Lobby"]


@_retrying
def addendum_takeoff(rng: random.Random, i: int) -> Task:
    n = rng.randint(15, 22)
    codes = list(PRODUCTS)
    rooms = []
    for k in range(n):
        rooms.append([str(101 + k), ROOMS[k % len(ROOMS)], rng.randint(96, 420), rng.randint(84, 300),
                      pick(rng, codes), rng.randint(1, 3)])
    ids = [r[0] for r in rooms]
    a1 = rng.sample(ids, 4)
    to1 = pick(rng, codes)
    a2_room = pick(rng, a1)
    to2 = pick(rng, [c for c in codes if c != to1])
    nic = pick(rng, [x for x in ids if x not in a1])
    a3 = rng.sample([x for x in ids if x not in a1 and x != nic], 2)
    to3 = pick(rng, codes)
    finish = {r[0]: r[4] for r in rooms}
    for x in a1:
        finish[x] = to1
    finish[a2_room] = to2
    for x in a3:
        finish[x] = to3
    area = {c: 0.0 for c in codes}
    base_lf = 0.0
    for rid, _, L, W, _, doors in rooms:
        if rid == nic:
            continue
        area[finish[rid]] += L * W / 144
        base_lf += 2 * (L + W) / 12 - 3.0 * doors
    tax = 0.08875
    packs, material = {}, 0.0
    for c, (_, unit, cover, waste, price) in PRODUCTS.items():
        q = area[c] * (1 + waste) / cover
        if area[c] and q - math.floor(q) < 1e-6:
            raise Retry
        packs[c] = math.ceil(q - 1e-9) if area[c] else 0
        material += packs[c] * price
    rolls = math.ceil(base_lf * 1.03 / 120 - 1e-9)
    material += rolls * 96.0
    total = material * (1 + tax)
    rows = "\n".join(f"| {rid} | {nm} | {ft_in(L)} × {ft_in(W)} | {f} | {d} |" for rid, nm, L, W, f, d in rooms)
    prods = "\n".join(f"- {c}: {d}, sold by the {u} covering {cv:g} sq ft, waste {w:.0%}, ${p:.2f} per {u}"
                      for c, (d, u, cv, w, p) in PRODUCTS.items())
    fields = {f"packages_{c.replace('-', '').lower()}": INTEGER for c in codes}
    fields.update({"base_rolls": INTEGER, "material_total_with_tax": number(0.001)})
    prompt = (
        "Floor-finish takeoff for a tenant fit-out. Room finish schedule (inside dimensions, feet-inches):\n\n"
        "| Room | Name | Size | Floor finish | Doors |\n|---|---|---|---|---|\n" + rows + "\n\n"
        f"Addendum 1: rooms {', '.join(a1)} change to {to1}.\n"
        f"Addendum 2: room {a2_room} changes to {to2} (supersedes Addendum 1 for that room).\n"
        f"Addendum 3: room {nic} is not in contract (delete it entirely); rooms {', '.join(a3)} change to {to3}.\n\n"
        f"Products:\n{prods}\n- RB-1 rubber base in every room in contract: rolls of 120 lf, waste 3%, $96.00 per roll. "
        "Base length per room = room perimeter − 3 ft for each door.\n\n"
        "Method: total each product's net quantity over all rooms in contract (sq ft = length × width), add that "
        "product's waste to the total, divide by the package coverage and round up to whole packages (a product with no "
        "area needs 0 packages). Material total = packages × unit prices for all products and base, plus 8.875% sales "
        "tax.\n\nGive the packages of each floor product, the rolls of base, and the material total with tax.\n"
        + answer_keys_line(fields))
    ans = {f"packages_{c.replace('-', '').lower()}": packs[c] for c in codes}
    ans.update({"base_rolls": rolls, "material_total_with_tax": round(total, 2)})
    return Task(f"z-takeoff-{i:04d}", "estimating", "addendum_takeoff", "Finish takeoff through three addenda", EXTREME,
                prompt, ans, fields, {"rooms": n})


# ---------------------------------------------------------------- finance: large three-job ledger with reclasses

@_retrying
def ledger_xl(rng: random.Random, i: int) -> Task:
    jobs = list(dict.fromkeys(job_no(rng) for _ in range(3)))
    if len(jobs) < 3:
        raise Retry
    target = jobs[0]
    codes = [c.split()[0] for c in rng.sample(CODES, 10)]
    cutoff = dt.date(2026, 10, 31)
    rows, doc = [], rng.randint(20_000, 70_000)
    for _ in range(rng.randint(280, 380)):
        doc += rng.randint(1, 30)
        rows.append([dt.date(2026, 8, 1) + dt.timedelta(days=rng.randint(0, 120)), pick(rng, jobs), pick(rng, codes), "",
                     pick(rng, VENDORS), f"INV-{doc}", round(rng.uniform(120, 42_000), 2), "INV"])
    mine = [r for r in rows if r[1] == target and r[0] <= cutoff]
    dups = rng.sample(mine, rng.randint(5, 9))
    for r in dups:
        rows.append([r[0] + dt.timedelta(days=rng.randint(0, 4)), *r[1:]])
    rest = [r for r in mine if r not in dups]
    for r in rng.sample(rest, rng.randint(4, 7)):
        rows.append([min(cutoff, r[0] + dt.timedelta(days=rng.randint(1, 9))), r[1], r[2], "", r[4], r[5], r[6], "VOID"])
    for _ in range(rng.randint(4, 6)):
        doc += 1
        r = pick(rng, mine)
        rows.append([r[0], target, r[2], "", r[4], f"CM-{doc}", -round(rng.uniform(100, 5_000), 2), "CR"])
    for _ in range(rng.randint(4, 7)):                                   # reclasses between codes on the job
        doc += 1
        a, b = rng.sample(codes, 2)
        rows.append([dt.date(2026, 8, 1) + dt.timedelta(days=rng.randint(0, 120)), target, b, a, "Journal",
                     f"JE-{doc}", round(rng.uniform(500, 20_000), 2), "RC"])
    rows.sort(key=lambda r: (r[0], r[5]))
    voids = {(r[4], r[5]) for r in rows if r[7] == "VOID" and r[1] == target and r[0] <= cutoff}
    seen, dup, by = set(), 0, {c: 0.0 for c in codes}
    for d, j, code, frm, vendor, docno, amt, kind in rows:
        if j != target or d > cutoff or kind == "VOID":
            continue
        if kind == "INV":
            if (vendor, docno, amt) in seen:
                dup += 1
                continue
            seen.add((vendor, docno, amt))
            if (vendor, docno) in voids:
                continue
        if kind == "RC":
            by[frm] -= amt
        by[code] += amt
    budget = {c: round_to(max(v, 1_000) * rng.uniform(0.85, 1.2), 500) for c, v in by.items()}
    over = {c: by[c] - budget[c] for c in codes}
    worst = sorted(over, key=over.get, reverse=True)
    if over[worst[0]] <= 0 or over[worst[0]] - over[worst[1]] < 250 or any(abs(v) < 50 for v in over.values()):
        raise Retry
    asked = rng.sample(codes, 2)
    csv = "date,job,cost_code,reclass_from,vendor,document,amount,type\n" + "\n".join(
        f"{r[0].isoformat()},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]:.2f},{r[7]}" for r in rows)
    btable = "| Cost code | Budget |\n|---|---|\n" + "\n".join(f"| {c} | {money(budget[c])} |" for c in codes)
    fields = {"total_cost_to_date": number(0.0005), "first_code_cost": number(0.0005),
              "second_code_cost": number(0.0005), "duplicate_rows_removed": INTEGER, "codes_over_budget": SET,
              "largest_overrun_code": TEXT}
    prompt = (
        f"Job cost to date for job {target} from this three-job accounts-payable and journal export, as of "
        f"{cutoff.isoformat()} (inclusive).\nRules:\n- Only rows for {target} dated on or before the cut-off count.\n"
        "- INV: invoice. The same vendor, document number and amount appearing more than once as INV was entered twice: "
        "count it once (each extra copy is one duplicate row removed).\n- VOID cancels the invoice with the same vendor "
        "and document number: neither counts.\n- CR: credit memo; its negative amount counts.\n- RC: reclass journal — "
        "moves the amount from the code in reclass_from to the code in cost_code (subtract from one, add to the other; "
        "the job total is unchanged).\n\n"
        f"```csv\n{csv}\n```\n\nBudgets for {target}:\n\n{btable}\n\n"
        f"Give the total cost to date for {target}; the cost to date on {asked[0]} (first_code_cost) and on {asked[1]} "
        "(second_code_cost); the number of duplicate rows removed; every cost code over budget (code numbers only, e.g. "
        "\"03-300\"); and the code with the largest overrun.\n" + answer_keys_line(fields))
    return Task(f"z-ledger-{i:04d}", "finance", "ledger_xl", "Large three-job ledger with reclasses", EXTREME, prompt,
                {"total_cost_to_date": round(sum(by.values()), 2), "first_code_cost": round(by[asked[0]], 2),
                 "second_code_cost": round(by[asked[1]], 2), "duplicate_rows_removed": dup,
                 "codes_over_budget": sorted(c for c in codes if over[c] > 0), "largest_overrun_code": worst[0]},
                fields, {"rows": len(rows)})


# ---------------------------------------------------------------- finance: contractor cash-flow forecast

@_retrying
def cashflow_forecast(rng: random.Random, i: int) -> Task:
    n = rng.randint(8, 12)
    acts = []
    for k in range(n):
        start = 1 if k == 0 else rng.randint(1, 10)
        dur = rng.randint(1, 6)
        acts.append((ACTS[k % len(ACTS)], start, dur, round_to(rng.uniform(80_000, 1_400_000), 1_000)))
    last = max(s + d - 1 for _, s, d, _ in acts)
    markup, ret, lag, pay_split = rng.choice([0.08, 0.10, 0.12]), rng.choice([0.05, 0.10]), rng.choice([1, 2]), \
        rng.choice([0.6, 0.7, 0.8])
    horizon = last + lag + 3
    cost = [0.0] * (horizon + 2)
    for _, s, d, c in acts:
        for m in range(s, s + d):
            cost[m] += c / d
    pay = [0.0] * (horizon + 2)
    for m in range(1, last + 1):
        pay[m] += cost[m] * pay_split
        pay[m + 1] += cost[m] * (1 - pay_split)
    rec = [0.0] * (horizon + 2)
    retained = 0.0
    for m in range(1, last + 1):
        billed = cost[m] * (1 + markup)
        rec[m + lag] += billed * (1 - ret)
        retained += billed * ret
    rec[last + 3] += retained
    cum, series = 0.0, []
    for m in range(1, horizon + 1):
        cum += rec[m] - pay[m]
        series.append(cum)
    low = min(range(len(series)), key=lambda k: series[k])
    ordered = sorted(series)
    if ordered[1] - ordered[0] < 0.005 * abs(ordered[0]) or series[low] >= 0:
        raise Retry
    turns = next((k + 1 for k in range(low, len(series)) if series[k] >= 0), None)
    if turns is None:
        raise Retry
    rows = "\n".join(f"| {nm} | {s} | {d} | {money(c)} |" for nm, s, d, c in acts)
    fields = {"peak_deficit": number(0.001), "peak_deficit_month": INTEGER, "first_month_back_to_positive": INTEGER,
              "final_cash_position": number(0.001)}
    prompt = (
        "Forecast the general contractor's cumulative cash position month by month.\n\n"
        "| Activity | Start month | Duration (months) | Cost |\n|---|---|---|---|\n" + rows + "\n\n"
        "Rules: each activity's cost is spread evenly over the months it runs (start month through start + duration − 1). "
        f"The contractor pays {pay_split:.0%} of each month's cost in that month and the rest in the following month. "
        f"It bills each month's cost plus {markup:.0%} markup at the end of that month; the owner withholds {ret:.0%} "
        f"retainage and pays the rest {lag} month{'s' if lag > 1 else ''} after the billing month. All retainage is "
        "released in one payment in the third month after the last month of work. Cash position starts at 0 before month "
        "1; the position for a month is the running total of receipts minus payments through the end of that month.\n\n"
        "Give the largest deficit (as a negative number), the month in which it occurs, the first month after that in which "
        "the position is zero or better, and the final cash position after the retainage payment.\n"
        + answer_keys_line(fields))
    return Task(f"z-cash-{i:04d}", "finance", "cashflow_forecast", "Contractor cash-flow forecast", EXTREME, prompt,
                {"peak_deficit": round(series[low], 2), "peak_deficit_month": low + 1, "first_month_back_to_positive": turns,
                 "final_cash_position": round(series[-1], 2)}, fields, {"activities": n})


ACTS = ["Sitework", "Foundations", "Structure", "Envelope", "Roofing", "MEP rough-in", "Interiors", "MEP finish",
        "Elevators", "Finishes", "Sitework finish", "Closeout"]
