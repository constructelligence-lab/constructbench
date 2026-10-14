"""Expert tier: tasks sized and layered like real work, so they cannot be done reliably in one's head.

Each family combines volume (20–150 rows), several interacting conventions and at least one trap that real documents
carry (a pending change order billed anyway, a duplicate invoice, a time-barred claim, amounts in words that differ
from the figures). Every convention is stated in the prompt and every answer is computed here from the same numbers
the prompt prints — one right answer, nothing hand-keyed. Generators retry with the same rng when a draw would make
an answer ambiguous (ties, a percentage sitting on a threshold), so a seed still rebuilds byte for byte.
"""
from __future__ import annotations

import datetime as dt
import random

from ..task import Task, number, INTEGER, TEXT, DATE, SET, answer_keys_line
from .common import JOB_NAMES, VENDORS, job_no, money, pick, round_to

EXPERT = "expert"
ACTIVITY = ["Mobilize", "Survey & layout", "Excavate", "Footings", "Foundation walls", "Waterproofing", "Backfill",
            "Underground plumbing", "Slab on grade", "Steel erection", "Metal deck", "Deck pour", "Roofing",
            "Curtain wall", "Masonry", "Framing", "MEP rough-in", "Fire sprinkler", "Insulation", "Drywall",
            "Taping", "Ceiling grid", "Paint", "Flooring", "Casework", "Elevator", "Fixtures", "Site paving",
            "Landscape", "Testing & balancing", "Commissioning", "Punch list"]


class Retry(Exception):
    """A draw that would make an answer ambiguous; the family draws again from the same rng."""


def _retrying(fn):
    def wrapper(rng: random.Random, i: int) -> Task:
        for _ in range(200):
            try:
                return fn(rng, i)
            except Retry:
                continue
        raise RuntimeError(f"{fn.__name__}: no unambiguous draw in 200 tries")
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


# ---------------------------------------------------------------- scheduling: PDM network on a working calendar

def pdm(ids, dur, preds):
    """Forward/backward pass with FS/SS/FF relationships and lags (all in workdays). EF = ES + duration;
    FS: ES_j >= EF_i + lag; SS: ES_j >= ES_i + lag; FF: EF_j >= EF_i + lag; nothing starts before day 0."""
    es, ef = {}, {}
    for a in ids:
        s = 0
        for p, t, lag in preds[a]:
            s = max(s, {"FS": ef[p] + lag, "SS": es[p] + lag, "FF": ef[p] + lag - dur[a]}[t])
        es[a], ef[a] = s, s + dur[a]
    project = max(ef.values())
    succ = {a: [] for a in ids}
    for b in ids:
        for p, t, lag in preds[b]:
            succ[p].append((b, t, lag))
    ls, lf = {}, {}
    for a in reversed(ids):
        f = project
        for s, t, lag in succ[a]:
            f = min(f, {"FS": ls[s] - lag, "SS": ls[s] - lag + dur[a], "FF": lf[s] - lag}[t])
        lf[a], ls[a] = f, f - dur[a]
    tf = {a: ls[a] - es[a] for a in ids}
    return {"es": es, "ef": ef, "ls": ls, "lf": lf, "tf": tf, "project": project}


def workdays(start: dt.date, holidays: set[dt.date], n: int) -> list[dt.date]:
    """The first n working days from `start` (Mon–Fri, not a holiday); index 0 is `start` itself."""
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5 and d not in holidays:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


@_retrying
def pdm_calendar(rng: random.Random, i: int) -> Task:
    n = rng.randint(24, 32)
    ids = [f"A{(k + 1) * 10:03d}" for k in range(n)]
    dur = {a: rng.randint(2, 18) for a in ids}
    dur[ids[0]] = rng.randint(1, 4)
    preds: dict[str, list] = {ids[0]: []}
    for k in range(1, n):
        cands = ids[max(0, k - 6):k]
        rel = []
        for p in rng.sample(cands, min(rng.choice([1, 1, 2, 2, 3]), len(cands))):
            t = rng.choices(["FS", "SS", "FF"], weights=[6, 2, 2])[0]
            lag = {"FS": rng.choice([0, 0, 0, 1, 2, 3, 5]), "SS": rng.randint(1, 8), "FF": rng.choice([0, 1, 2, 3, 5])}[t]
            rel.append((p, t, lag))
        preds[ids[k]] = rel
    c = pdm(ids, dur, preds)
    if min(c["tf"].values()) < 0:
        raise Retry
    crit = [a for a in ids if c["tf"][a] == 0]
    floaty = [a for a in ids if c["tf"][a] > 0]
    late = [a for a in ids if c["es"][a] > 10 and a not in crit]
    if not floaty or not late:
        raise Retry
    x, y = pick(rng, floaty), pick(rng, late)
    start = dt.date(2026, 1, 5) + dt.timedelta(weeks=rng.randint(0, 40))          # a Monday
    pool = [start + dt.timedelta(days=d) for d in range(3, 7 * 40)]
    holidays = sorted(rng.sample([d for d in pool if d.weekday() < 5], rng.randint(4, 7)))
    cal = workdays(start, set(holidays), c["project"] + 1)
    finish_date, y_start = cal[c["project"] - 1], cal[c["es"][y]]

    def fmt(ps):
        return ", ".join(f"{p} {t}" + (f"+{lag}" if lag else "") for p, t, lag in ps) or "—"
    table = "| ID | Activity | Duration | Predecessors |\n|---|---|---|---|\n" + "\n".join(
        f"| {a} | {ACTIVITY[k % len(ACTIVITY)]} | {dur[a]} | {fmt(preds[a])} |" for k, a in enumerate(ids))
    fields = {"project_duration_workdays": INTEGER, "project_finish_date": DATE, "critical_activities": SET,
              f"total_float_{x}": INTEGER, f"early_start_date_{y}": DATE}
    prompt = (
        "Precedence-diagram schedule for a mid-rise building. Durations and lags are in working days.\n"
        "Conventions (day numbers): an activity with early start ES and duration d has early finish EF = ES + d and "
        "works on days ES … EF−1. Relationship \"P FS+n\": the activity's ES ≥ EF(P) + n. \"P SS+n\": its ES ≥ ES(P) + n. "
        "\"P FF+n\": its EF ≥ EF(P) + n. A relationship without +n has lag 0. No activity starts before day 0. Project "
        "duration = the largest EF. Backward pass from the project duration (every activity's latest finish is at most "
        "the project duration), mirroring the same three rules; total float = LS − ES; critical = total float 0.\n"
        f"Calendar: day 0 is {start.isoformat()} (a Monday). Working days are Monday–Friday except these holidays: "
        f"{', '.join(h.isoformat() for h in holidays)}. Day k is the k-th working day after day 0. An activity's start "
        "date is the date of day ES; the project finish date is the date of the last working day, day (duration − 1).\n\n"
        f"{table}\n\nGive the project duration in working days, the project finish date, every critical activity, the total "
        f"float of {x}, and the early start date of {y}.\n" + answer_keys_line(fields))
    return Task(f"x-pdm-{i:04d}", "scheduling", "pdm_calendar", "PDM schedule on a working calendar", EXPERT, prompt,
                {"project_duration_workdays": c["project"], "project_finish_date": finish_date.isoformat(),
                 "critical_activities": crit, f"total_float_{x}": c["tf"][x], f"early_start_date_{y}": y_start.isoformat()},
                fields, {"activities": n})


# ---------------------------------------------------------------- finance: pay application certification

SOV = ["General conditions", "Sitework", "Concrete foundations", "Structural steel", "Masonry", "Rough carpentry",
       "Roofing", "Waterproofing", "Doors & hardware", "Glazing", "Drywall & framing", "Acoustical ceilings",
       "Flooring", "Painting", "Specialties", "Fire protection", "Plumbing", "HVAC", "Electrical", "Fire alarm",
       "Low voltage", "Elevator", "Site utilities", "Paving", "Landscaping", "Final cleaning", "Casework",
       "Insulation", "Toilet accessories", "Signage"]


@_retrying
def pay_app_certification(rng: random.Random, i: int) -> Task:
    n_base = rng.randint(20, 26)
    lines = []                                        # (item, desc, C, D, E, F, approved)
    stage = rng.uniform(0.05, 0.6)                   # how far along the whole job is
    for k in range(n_base):
        C = round_to(rng.uniform(15_000, 420_000), 500)
        prev = min(0.9, max(0.0, stage + rng.uniform(-0.25, 0.25)))
        D = round_to(C * prev, 100)
        E = round_to(C * rng.uniform(0, min(0.35, 1 - prev)), 100)
        F = round_to(rng.uniform(0, (C - D - E) * 0.6), 100) if rng.random() < .2 else 0
        lines.append([str(k + 1), SOV[k % len(SOV)], C, D, E, F, True])
    for j in range(rng.randint(2, 3)):
        C = round_to(rng.uniform(4_000, 60_000), 100)
        E = round_to(C * rng.uniform(0.2, 1.0), 100)
        lines.append([str(len(lines) + 1), f"CO-{j + 1:02d} approved change order", C, 0, E, 0, True])
    pending = []
    for j in range(rng.randint(1, 2)):
        C = round_to(rng.uniform(5_000, 45_000), 100)
        E = round_to(C * rng.uniform(0.3, 1.0), 100)
        item = str(len(lines) + 1)
        pending.append(item)
        lines.append([item, f"PCO-{j + 7:02d} proposed change (pending — not approved)", C, 0, E, 0, False])
    printed = {}
    for item, _, C, D, E, F, _ in lines:
        G = D + E + F
        printed[item] = (G, C - G)
    approved_items = [l[0] for l in lines if l[6]]
    errors = rng.sample(approved_items, rng.randint(2, 4))
    for item in errors:
        G, H = printed[item]
        delta = round_to(rng.uniform(1_000, 25_000), 100)
        if G - delta >= 0 and rng.random() < .5:
            delta = -delta
        printed[item] = (G + delta, H - delta) if rng.random() < .6 else (G, H + delta)   # wrong G (H follows) or wrong H
    ok = [l for l in lines if l[6]]
    sumC = sum(l[2] for l in ok)
    sumDE = sum(l[3] + l[4] for l in ok)
    sumF = sum(l[5] for l in ok)
    sumG = sumDE + sumF
    pct = sumG / sumC
    if abs(pct - 0.5) < 0.03:
        raise Retry
    rate = 0.05 if pct > 0.5 else 0.10
    ret = rate * sumDE + 0.10 * sumF
    prev_cert = round(sum(l[3] for l in ok) * 0.9)
    due = sumG - ret - prev_cert
    rows = "\n".join(
        f"| {item} | {desc} | {money(C)} | {money(D)} | {money(E)} | {money(F)} | {money(printed[item][0])} | "
        f"{money(printed[item][1])} |" for item, desc, C, D, E, F, _ in lines)
    fields = {"error_lines": SET, "excluded_lines": SET, "corrected_total_completed_stored": number(0.001),
              "retainage": number(0.001), "current_payment_due": number(0.001)}
    prompt = (
        f"You are certifying a subcontractor's pay application (AIA G703-style continuation sheet) for {pick(rng, JOB_NAMES)}. "
        "Columns: C scheduled value, D work completed from previous applications, E work completed this period, F materials "
        "presently stored, G total completed and stored to date (should be D + E + F), H balance to finish (should be "
        "C − G).\n\nRules:\n"
        "1. A line has an arithmetic error if its printed G is not D + E + F, or its printed H is not C − (D + E + F). "
        "Columns C, D, E and F are correct as printed.\n"
        "2. Lines for changes that are pending (not approved) are excluded from the contract sum and from all billing "
        "totals, whatever has been billed on them.\n"
        "3. Use corrected figures (G = D + E + F) for every total.\n"
        "4. Percent complete = total G ÷ total C over the included lines. Retainage on completed work (D + E) is 10%, "
        "reduced to 5% for the whole job once percent complete is more than 50%. Retainage on stored materials (F) is "
        "always 10%.\n"
        f"5. Previous certificates for payment total {money(prev_cert)}. Current payment due = total G − retainage − "
        "previous certificates.\n\n"
        "| Item | Description | C | D | E | F | G (printed) | H (printed) |\n|---|---|---|---|---|---|---|---|\n" + rows +
        "\n\nGive the item numbers of lines with an arithmetic error and of lines excluded under rule 2 (item numbers only, "
        "as strings such as \"7\"), the corrected total completed and stored, the retainage, and the current payment due.\n"
        + answer_keys_line(fields))
    return Task(f"x-payapp-{i:04d}", "finance", "pay_app_certification", "Pay application certification", EXPERT, prompt,
                {"error_lines": sorted(errors, key=int), "excluded_lines": pending,
                 "corrected_total_completed_stored": sumG, "retainage": round(ret, 2),
                 "current_payment_due": round(due, 2)}, fields, {"lines": len(lines)})


# ---------------------------------------------------------------- finance: WIP schedule for a portfolio

@_retrying
def wip_portfolio(rng: random.Random, i: int) -> Task:
    n = rng.randint(14, 20)
    jobs, used = [], set()
    while len(jobs) < n:
        j = job_no(rng)
        if j in used:
            continue
        used.add(j)
        contract = round_to(rng.uniform(300_000, 12_000_000), 1_000)
        margin = rng.uniform(-0.08, 0.18)
        est = round_to(contract * (1 - margin), 100)
        pct = rng.uniform(0.05, 1.0)
        ctd = est if pct > 0.97 else round_to(est * pct, 100)
        earned_guess = ctd / est * contract
        billed = min(contract, round_to(earned_guess * rng.uniform(0.85, 1.15), 100))
        status = "Closed — final in prior fiscal year" if len(jobs) < 2 else "Open"
        jobs.append((j, status, contract, est, ctd, billed))
    rng.shuffle(jobs)
    over = under = provision = gp = 0.0
    unders = {}
    for j, status, contract, est, ctd, billed in jobs:
        if status != "Open":
            continue
        poc = ctd / est
        earned = poc * contract
        diff = billed - earned
        if diff > 0:
            over += diff
        else:
            under += -diff
            unders[j] = -diff
        prov = (est - contract) * (1 - poc) if est > contract else 0.0
        provision += prov
        gp += earned - ctd - prov
    top = sorted(unders.items(), key=lambda kv: -kv[1])
    if len(top) < 2 or top[0][1] < top[1][1] * 1.02:
        raise Retry
    rows = "\n".join(f"| {j} | {status} | {money(c)} | {money(e)} | {money(d)} | {money(b)} |"
                     for j, status, c, e, d, b in jobs)
    fields = {"billings_in_excess_total": number(0.001), "costs_in_excess_total": number(0.001),
              "provision_for_losses": number(0.001), "gross_profit_to_date": number(0.001), "most_underbilled_job": TEXT}
    prompt = (
        "Prepare the year-end work-in-progress (WIP) schedule totals for this contractor. Percentage-of-completion, "
        "cost-to-cost method.\nRules: only jobs with status Open are included. Percent complete = cost to date ÷ "
        "estimated total cost. Revenue earned = percent complete × contract value. Billings in excess of costs and "
        "estimated earnings (over-billing) = billed − earned where positive; costs and estimated earnings in excess of "
        "billings (under-billing) = earned − billed where positive; report each as a total over jobs (do not net jobs "
        "against each other). For a job whose estimated total cost exceeds its contract value, the whole projected loss "
        "is recognized now: provision for losses = projected loss × (1 − percent complete), and that job's gross profit "
        "to date = earned − cost to date − provision. Other jobs: gross profit to date = earned − cost to date.\n\n"
        "| Job | Status | Contract value | Estimated total cost | Cost to date | Billed to date |\n|---|---|---|---|---|---|\n"
        + rows + "\n\nGive the over-billing total, the under-billing total, the total provision for losses, total gross "
        "profit to date, and the job number with the largest under-billing.\n" + answer_keys_line(fields))
    return Task(f"x-wip-{i:04d}", "finance", "wip_portfolio", "WIP schedule for a portfolio", EXPERT, prompt,
                {"billings_in_excess_total": round(over, 2), "costs_in_excess_total": round(under, 2),
                 "provision_for_losses": round(provision, 2), "gross_profit_to_date": round(gp, 2),
                 "most_underbilled_job": top[0][0]}, fields, {"jobs": n})


# ---------------------------------------------------------------- finance: cost ledger roll-up from raw entries

CODES = ["01-500 Temporary facilities", "03-300 Cast-in-place concrete", "04-200 Unit masonry", "05-120 Structural steel",
         "06-100 Rough carpentry", "07-500 Membrane roofing", "08-400 Storefronts", "09-250 Gypsum board",
         "09-900 Painting", "22-000 Plumbing", "23-000 HVAC", "26-000 Electrical"]


@_retrying
def cost_ledger(rng: random.Random, i: int) -> Task:
    target, others = job_no(rng), [job_no(rng) for _ in range(2)]
    if target in others or others[0] == others[1]:
        raise Retry
    codes = rng.sample(CODES, 8)
    cutoff = dt.date(2026, 10, 15)
    rows, inv_no = [], rng.randint(10_000, 60_000)
    for _ in range(rng.randint(110, 140)):
        inv_no += rng.randint(1, 40)
        job = target if rng.random() < .7 else pick(rng, others)
        d = dt.date(2026, 9, 1) + dt.timedelta(days=rng.randint(0, 59))
        rows.append([d, job, pick(rng, codes).split()[0], pick(rng, VENDORS), f"INV-{inv_no}",
                     round(rng.uniform(250, 38_000), 2), "INV"])
    base = [r for r in rows if r[1] == target and r[0] <= cutoff]
    dups = rng.sample(base, rng.randint(4, 7))
    for r in dups:
        rows.append([r[0] + dt.timedelta(days=rng.randint(0, 6)), *r[1:]])
    rest = [r for r in base if r not in dups]
    voided = rng.sample(rest, rng.randint(3, 5))
    for r in voided:
        rows.append([min(cutoff, r[0] + dt.timedelta(days=rng.randint(1, 10))), r[1], r[2], r[3], r[4], r[5], "VOID"])
    for _ in range(rng.randint(3, 5)):
        inv_no += 1
        r = pick(rng, base)
        rows.append([r[0] + dt.timedelta(days=rng.randint(0, 5)), target, r[2], r[3], f"CM-{inv_no}",
                     -round(rng.uniform(150, 4_000), 2), "CR"])
    rows.sort(key=lambda r: (r[0], r[4]))
    # reference roll-up, independent of how the rows were made
    seen, actual, n_dup = set(), {c.split()[0]: 0.0 for c in codes}, 0
    voids = {(r[3], r[4]) for r in rows if r[6] == "VOID" and r[1] == target and r[0] <= cutoff}
    for r in rows:
        if r[1] != target or r[0] > cutoff or r[6] == "VOID":
            continue
        key = (r[3], r[4], r[5])
        if r[6] == "INV":
            if key in seen:
                n_dup += 1
                continue
            seen.add(key)
            if (r[3], r[4]) in voids:
                continue
        actual[r[2]] += r[5]
    budget = {c: round_to(v * rng.uniform(0.82, 1.22), 500) if v > 0 else 5_000 for c, v in actual.items()}
    overrun = sorted(((actual[c] - budget[c], c) for c in actual), reverse=True)
    if overrun[0][0] <= 0 or overrun[0][0] - overrun[1][0] < 200:
        raise Retry
    asked = pick(rng, [c for c in actual if actual[c] > 0])
    csv = "date,job,cost_code,vendor,document,amount,type\n" + "\n".join(
        f"{r[0].isoformat()},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]:.2f},{r[6]}" for r in rows)
    btable = "| Cost code | Budget |\n|---|---|\n" + "\n".join(
        f"| {c} | {money(budget[c.split()[0]])} |" for c in codes)
    fields = {"total_cost_to_date": number(0.0005), "asked_code_cost": number(0.0005), "duplicate_rows_removed": INTEGER,
              "largest_overrun_code": TEXT, "largest_overrun_amount": number(0.001)}
    prompt = (
        f"Roll up job cost to date for job {target} from the accounts-payable export below, as of the cut-off date "
        f"{cutoff.isoformat()} (inclusive).\nRules:\n- Only rows for job {target} dated on or before the cut-off count.\n"
        "- type INV is an invoice. If the same vendor, document number and amount appear more than once as INV, it was "
        "entered twice: count it once (each extra copy is one duplicate row removed).\n"
        "- type VOID cancels the invoice with the same vendor and document number: neither the invoice nor the VOID "
        "row counts.\n- type CR is a credit memo: its (negative) amount counts.\n\n"
        f"```csv\n{csv}\n```\n\nBudgets for job {target}:\n\n{btable}\n\n"
        f"Give the total cost to date for {target}, the cost to date on cost code {asked} (asked_code_cost), the number of duplicate rows "
        "removed, and the cost code (number only, e.g. \"03-300\") with the largest overrun (cost to date − budget) "
        "and that overrun.\n" + answer_keys_line(fields))
    return Task(f"x-ledger-{i:04d}", "finance", "cost_ledger", "Job cost roll-up from a raw AP export", EXPERT, prompt,
                {"total_cost_to_date": round(sum(actual.values()), 2), "asked_code_cost": round(actual[asked], 2),
                 "duplicate_rows_removed": n_dup, "largest_overrun_code": overrun[0][1],
                 "largest_overrun_amount": round(overrun[0][0], 2)}, fields, {"rows": len(rows)})


# ---------------------------------------------------------------- civil: earthwork and the mass-haul diagram

def station(ft: int) -> str:
    return f"{ft // 100}+{ft % 100:02d}"


@_retrying
def mass_haul(rng: random.Random, i: int) -> Task:
    n = rng.randint(21, 31)
    step, s0 = 50, rng.choice([1000, 2000, 5000])
    shrink = rng.choice([0.10, 0.12, 0.15, 0.18, 0.20])
    import math
    period, phase, amp = rng.uniform(10, 18), rng.uniform(0, 6.28), rng.uniform(3, 6)
    drift = rng.uniform(-0.08, 0.08)
    cut, fill = [], []
    for k in range(n):
        h = amp * math.sin(2 * math.pi * k / period + phase) + drift * k + rng.uniform(-0.6, 0.6)
        c = max(0.0, h) * rng.uniform(55, 80) + (rng.uniform(0, 25) if abs(h) < 0.8 else 0)
        f = max(0.0, -h) * rng.uniform(55, 80) + (rng.uniform(0, 25) if abs(h) < 0.8 else 0)
        cut.append(round(c)); fill.append(round(f))
    tot_cut = tot_fill = 0.0
    m, ords = 0.0, [0.0]
    for k in range(n - 1):
        cv = (cut[k] + cut[k + 1]) / 2 * step / 27
        fv = (fill[k] + fill[k + 1]) / 2 * step / 27
        tot_cut += cv; tot_fill += fv
        m += cv * (1 - shrink) - fv
        ords.append(m)
    top = sorted(range(n), key=lambda k: -ords[k])
    if tot_fill < 0.3 * tot_cut * (1 - shrink) or tot_cut < 0.3 * tot_fill or top[0] in (0, n - 1):
        raise Retry
    if ords[top[0]] <= 0 or ords[top[0]] - ords[top[1]] < max(5.0, 0.01 * ords[top[0]]):
        raise Retry
    net = ords[-1] / (1 - shrink)
    if abs(net) < 20:
        raise Retry
    rows = "\n".join(f"| {station(s0 + k * step)} | {cut[k]} | {fill[k]} |" for k in range(n))
    fields = {"total_cut_bcy": number(0.002), "total_fill_ccy": number(0.002), "net_bcy": number(0.005),
              "max_ordinate_ccy": number(0.005), "max_ordinate_station": TEXT}
    prompt = (
        f"Roadway earthwork. Cross-section end areas (sq ft) every {step} ft are below. Volumes between adjacent "
        "stations use the average-end-area method (cubic yards = (A1 + A2) / 2 × length ÷ 27). Cut volumes are bank "
        f"cubic yards (bcy); fill volumes are compacted cubic yards (ccy). Shrinkage is {shrink:.0%}: 1 bcy of cut makes "
        f"{1 - shrink:.2f} ccy of fill.\nMass-haul ordinate: 0 at the first station; at each next station add that "
        f"interval's cut × {1 - shrink:.2f} and subtract its fill (ordinates in ccy).\n\n"
        "| Station | Cut area | Fill area |\n|---|---|---|\n" + rows +
        "\n\nGive total cut (bcy), total fill (ccy), the net balance in bank cubic yards (final ordinate ÷ "
        f"{1 - shrink:.2f}; positive = surplus to export, negative = borrow to import), the largest mass-haul ordinate "
        "(ccy) and the station where it occurs (as printed, e.g. \"12+50\").\n" + answer_keys_line(fields))
    return Task(f"x-haul-{i:04d}", "civil", "mass_haul", "Earthwork and mass-haul ordinates", EXPERT, prompt,
                {"total_cut_bcy": round(tot_cut, 2), "total_fill_ccy": round(tot_fill, 2), "net_bcy": round(net, 2),
                 "max_ordinate_ccy": round(ords[top[0]], 2), "max_ordinate_station": station(s0 + top[0] * step)},
                fields, {"stations": n})


# ---------------------------------------------------------------- contracts: time-impact analysis with concurrency

@_retrying
def delay_tia(rng: random.Random, i: int) -> Task:
    ntp = dt.date(2025, 3, 3) + dt.timedelta(days=rng.randint(0, 200))
    duration = rng.choice([365, 420, 480, 540])
    original = ntp + dt.timedelta(days=duration)
    rate = rng.choice([1_500, 2_500, 3_000, 4_000, 5_000])
    window = 300
    causes = {"Owner": ["Late design change to lobby", "Owner-furnished equipment late", "Late approval of shop drawings",
                        "Differing site condition (rock)", "Owner suspension of work"],
              "Contractor": ["Steel fabricator late delivery", "Crane breakdown", "Rework of failed slab pour",
                             "Subcontractor manpower shortage"],
              "Weather": ["Abnormal rainfall", "Hurricane shutdown", "Extreme cold — no concrete placement"]}
    events = []
    for k in range(rng.randint(6, 9)):
        who = rng.choices(["Owner", "Contractor", "Weather"], weights=[4, 3, 2])[0]
        s = ntp + dt.timedelta(days=rng.randint(20, window))
        e = s + dt.timedelta(days=rng.randint(3, 40) - 1)
        critical = rng.random() < .8
        notice = s + dt.timedelta(days=rng.choice([1, 3, 5, 7, 10, 14, 20, 25, 34]))
        events.append((f"E{k + 1}", pick(rng, causes[who]), who, s, e, critical, notice))
    events.sort(key=lambda ev: ev[3])
    events = [(f"E{k + 1}", *ev[1:]) for k, ev in enumerate(events)]
    counted = [ev for ev in events if ev[5] and (ev[2] == "Contractor" or (ev[6] - ev[3]).days <= 21)]
    exc = comp = 0
    d = min(ev[3] for ev in events)
    last = max(ev[4] for ev in events)
    while d <= last:
        who = {ev[2] for ev in counted if ev[3] <= d <= ev[4]}
        if who and who != {"Contractor"}:
            exc += 1
            if who == {"Owner"}:
                comp += 1
        d += dt.timedelta(days=1)
    extended = original + dt.timedelta(days=exc)
    actual = extended + dt.timedelta(days=rng.randint(-20, 60))
    ld_days = max(0, (actual - extended).days)
    if exc == 0 or comp == 0:
        raise Retry
    rows = "\n".join(f"| {e} | {desc} | {who} | {s.isoformat()} | {f.isoformat()} | {'Yes' if crit else 'No'} | "
                     f"{notice.isoformat()} |" for e, desc, who, s, f, crit, notice in events)
    fields = {"extension_days": INTEGER, "compensable_days": INTEGER, "extended_completion_date": DATE,
              "ld_days": INTEGER, "ld_amount": number(0.0001)}
    prompt = (
        f"Contract: notice to proceed {ntp.isoformat()}, contract completion date {original.isoformat()}, liquidated "
        f"damages {money(rate)} per calendar day. Actual substantial completion: {actual.isoformat()}.\n"
        "Delay events (dates inclusive; all days are calendar days):\n\n"
        "| Event | Description | Responsibility | Start | End | On the critical path | Written notice given |\n"
        "|---|---|---|---|---|---|---|\n" + rows + "\n\n"
        "Contract rules:\n1. Only events on the critical path can extend the contract time.\n"
        "2. For Owner and Weather events, written notice must be given within 21 calendar days after the event starts "
        "(day 21 is still on time); an event with late notice is disregarded entirely. Contractor events need no notice.\n"
        "3. Classify each calendar day by the responsibilities of the counted events active that day: Owner only → "
        "excusable and compensable; Contractor only → not excusable; any other combination (Weather alone, Weather "
        "with Owner, or Contractor together with Owner and/or Weather) → excusable, not compensable. A day counts once "
        "however many events are active.\n"
        "4. The contract time is extended by the number of excusable days; liquidated damages apply to each day from "
        "the extended completion date to actual substantial completion (0 if completed on or before it).\n\n"
        "Give the extension in days, the compensable days, the extended completion date, the days of liquidated "
        "damages and the liquidated damages amount.\n" + answer_keys_line(fields))
    return Task(f"x-tia-{i:04d}", "contracts", "delay_tia", "Time-impact analysis with concurrency and notice",
                EXPERT, prompt, {"extension_days": exc, "compensable_days": comp,
                                 "extended_completion_date": extended.isoformat(), "ld_days": ld_days,
                                 "ld_amount": ld_days * rate}, fields, {"events": len(events)})


# ---------------------------------------------------------------- preconstruction: leveling a bid with traps

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
        "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def words(n: int) -> str:
    """Whole dollars in words as written on a bid form: 2,345,670 -> 'two million three hundred forty-five thousand
    six hundred seventy'."""
    def under_1000(x: int) -> str:
        out = []
        if x >= 100:
            out.append(f"{ONES[x // 100]} hundred")
            x %= 100
        if x >= 20:
            out.append(TENS[x // 10] + (f"-{ONES[x % 10]}" if x % 10 else ""))
        elif x:
            out.append(ONES[x])
        return " ".join(out)
    if n == 0:
        return "zero"
    parts = []
    for size, name in ((1_000_000, "million"), (1_000, "thousand"), (1, "")):
        if n >= size:
            parts.append((under_1000(n // size) + (f" {name}" if name else "")).strip())
            n %= size
    return " ".join(parts)


SUBS = {"Mechanical": ["Copperline Mechanical", "Northfield Plumbing & Heating", "Airflow Systems", "Meridian HVAC",
                       "Tri-County Mechanical", "Baystate Comfort"],
        "Electrical": ["Voltline Electric", "Brightway Electrical", "Current Power & Light", "Gridline Electric",
                       "Halvorsen Electrical", "Arcwell Contractors"],
        "Structural steel": ["Ironwood Steel Erectors", "Keel Steel", "Ridgeback Fabricators", "Lattice Steel",
                             "Anvil Structural", "Tallpine Steel"],
        "Concrete": ["Granite State Concrete", "Formwell Concrete", "Bedrock Builders", "Slabline Concrete",
                     "Aggregate Partners", "Cornerstone Flatwork"],
        "Drywall & framing": ["Summit Drywall & Acoustics", "Plumbline Interiors", "Studwell Framing", "Level Five Walls",
                              "Ceilingworks", "Partition Pros"]}

SCOPE = ["Layout & surveying", "Dewatering", "Rock excavation", "Winter protection", "Firestopping", "Temporary power",
         "Testing & inspection fees", "Hoisting", "Cleanup & dumpsters", "Engineering of connections", "Bonding of piping",
         "Permit fees", "Patch & repair", "Seismic bracing", "Shop drawings & submittals"]


@_retrying
def bid_leveling_expert(rng: random.Random, i: int) -> Task:
    trade = pick(rng, ["Mechanical", "Electrical", "Structural steel", "Concrete", "Drywall & framing"])
    items = rng.sample(SCOPE, 12)
    plugs = {it: round_to(rng.uniform(3_000, 85_000), 500) for it in items}
    bond_rate = rng.choice([0.009, 0.012, 0.015])
    alt_desc = pick(rng, ["Alternate 1: upgraded controls", "Alternate 1: extended warranty", "Alternate 1: added level of parking"])
    names = rng.sample(SUBS[trade], 5)
    base_cost = rng.uniform(1_200_000, 6_500_000)
    bidders = []
    for nm in names:
        fig = round_to(base_cost * rng.uniform(0.9, 1.1), 100)
        status = {}
        for it in items:
            r = rng.random()
            status[it] = "Excl" if r < .18 else (f"Allow {money(round_to(plugs[it] * rng.uniform(0.4, 1.3), 500))}"
                                                 if r < .28 else "Incl")
        bidders.append({"name": nm, "words": fig, "figures": fig, "status": status, "bond": rng.random() < .6,
                        "alt": round_to(rng.uniform(20_000, 140_000), 500)})
    for b in rng.sample(bidders, rng.randint(1, 2)):          # figures written wrong on the form; words govern
        s = str(b["words"])
        k = rng.randrange(len(s) - 3)
        swapped = s[:k] + s[k + 1] + s[k] + s[k + 2:]
        b["figures"] = int(swapped) if swapped != s else b["words"] + 9_000
    leveled = {}
    for b in bidders:
        total = b["words"] + b["alt"]
        for it in items:
            st = b["status"][it]
            if st == "Excl":
                total += plugs[it]
            elif st.startswith("Allow"):
                allow = float(st.split("$")[1].replace(",", ""))
                total += max(0.0, plugs[it] - allow)
        if not b["bond"]:
            total *= 1 + bond_rate
        leveled[b["name"]] = total
    order = sorted(leveled, key=leveled.get)
    if leveled[order[1]] - leveled[order[0]] < 0.004 * leveled[order[0]]:
        raise Retry
    figures_low = min(bidders, key=lambda b: b["figures"])["name"]
    if figures_low == order[0] and rng.random() < .5:
        raise Retry                                          # keep the "lowest base bid is not the low bidder" trap common
    head = "| Scope item | Plug | " + " | ".join(b["name"] for b in bidders) + " |\n|---|---|" + "---|" * len(bidders)
    body = "\n".join(f"| {it} | {money(plugs[it])} | " + " | ".join(b["status"][it] for b in bidders) + " |" for it in items)
    forms = "\n".join(f"- {b['name']}: base bid in figures {money(b['figures'])}; in words \"{words(b['words'])} dollars\"; "
                      f"bond {'included' if b['bond'] else 'NOT included'}; {alt_desc}: add {money(b['alt'])}"
                      for b in bidders)
    fields = {"low_bidder": TEXT, "low_leveled_amount": number(0.0005), "second_leveled_amount": number(0.0005)}
    prompt = (
        f"Level these {trade} subcontract bids.\nBid forms:\n{forms}\n\nScope checklist (Incl = included; Excl = "
        "excluded; Allow $X = carries an allowance of $X for that item) with the estimator's plug for each item:\n\n"
        f"{head}\n{body}\n\nLeveling rules:\n1. Where the amount in words differs from the figures, the words govern.\n"
        "2. Add the plug for every excluded item. For an allowance item add (plug − allowance) when the plug is higher, "
        "nothing otherwise.\n3. The owner has accepted the alternate: add each bidder's alternate price.\n"
        f"4. A bidder that does not include a bond gets {bond_rate:.1%} added on its total after steps 1–3.\n\n"
        "Give the low bidder's name (as written), its leveled amount, and the second-lowest leveled amount.\n"
        + answer_keys_line(fields))
    return Task(f"x-level-{i:04d}", "preconstruction", "bid_leveling_expert", "Bid leveling with words, plugs and bonds",
                EXPERT, prompt, {"low_bidder": order[0], "low_leveled_amount": round(leveled[order[0]], 2),
                                 "second_leveled_amount": round(leveled[order[1]], 2)}, fields, {"bidders": 5})
