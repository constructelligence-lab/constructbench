"""Hidden-rule and chained tasks.

Hidden rules: the prompt asks for the work "per the contract"; the governing rules sit in a numbered contract
excerpt among clauses that do not apply (several carrying numbers). Each task draws its own rule variants (retainage
scheme, stored-materials terms, notice period, concurrency treatment, LD cap), so a model cannot fall back on a
customary rule — it has to find and apply the clause. Every rule that decides the answer is in the excerpt.

Chained: one job carried from quantity takeoff to estimate, bid, schedule and cash flow; each stage uses the stage
before. `chain_values(params, overrides)` recomputes every stage and lets an analysis substitute a model's own
upstream answers, separating the first error from errors carried forward.
"""
from __future__ import annotations

import datetime as dt
import math
import random

from ..task import Task, number, INTEGER, DATE, SET, answer_keys_line
from .common import JOB_NAMES, money, pick, round_to
from .expert import SOV, Retry, _retrying

EXTREME = "extreme"

DISTRACTORS = [
    "§4.2 Insurance. Subcontractor shall maintain commercial general liability insurance of not less than $2,000,000 "
    "per occurrence and $4,000,000 aggregate, and umbrella coverage of $5,000,000.",
    "§5.1 Indemnity. To the fullest extent permitted by law, Subcontractor shall indemnify the Contractor against "
    "claims arising out of Subcontractor's work, except to the extent caused by the Contractor's negligence.",
    "§6.4 Disputed work. Contractor may withhold up to 150% of the value of work that is the subject of a written "
    "dispute notice. (No dispute notice is open on this application.)",
    "§7.2 Cleanup. Subcontractor shall remove its debris daily; Contractor may clean up after 24 hours' notice and "
    "back-charge the cost plus 10%.",
    "§10.3 Warranty. Subcontractor warrants its work for one year from substantial completion, or two years for "
    "roofing and waterproofing.",
    "§11.1 Disputes. Claims of $250,000 or less are resolved by mediation followed by binding arbitration in the "
    "county where the project is located.",
    "§12.2 Termination for convenience. Contractor may terminate on 7 days' written notice; Subcontractor is paid for "
    "work performed plus 5% overhead and profit on that work, and no profit on work not performed.",
    "§13.1 Safety. Subcontractor shall attend weekly safety meetings and maintain an EMR of 1.0 or lower.",
    "§14.5 Notices. Notices are effective when delivered by hand or by email to the addresses in Exhibit A.",
]


def excerpt(rng: random.Random, title: str, clauses: list[str], prime: bool = False) -> str:
    """Clauses plus 4–6 distractors, in section order. `prime` rewrites the subcontract boilerplate for an
    Owner–Contractor agreement (Contractor → Owner, Subcontractor → Contractor)."""
    extra = rng.sample(DISTRACTORS, rng.randint(4, 6))
    if prime:
        extra = [c.replace("Subcontractor", "\0").replace("Contractor", "Owner").replace("\0", "Contractor")
                  .replace(" on this application", "") for c in extra]
    body = clauses + extra
    body.sort(key=lambda c: [int(x) for x in c.split()[0].lstrip("§").rstrip(".").split(".")])
    return f"--- document: {title} (excerpt) ---\n" + "\n".join(body) + "\n--- end ---"


# ---------------------------------------------------------------- pay application under contract payment terms

@_retrying
def pay_app_contract(rng: random.Random, i: int) -> Task:
    scheme = rng.choice(["step", "flat5", "ten_no_stored"])
    stored_rule = rng.choice(["all", "onsite_or_approved"])
    stage = rng.uniform(0.05, 0.6)
    lines = []
    for k in range(rng.randint(18, 24)):
        C = round_to(rng.uniform(15_000, 380_000), 500)
        prev = min(0.9, max(0.0, stage + rng.uniform(-0.25, 0.25)))
        D = round_to(C * prev, 100)
        E = round_to(C * rng.uniform(0, min(0.35, 1 - prev)), 100)
        F, loc = 0, "—"
        if rng.random() < .3:
            F = round_to(rng.uniform(2_000, max(2_100, (C - D - E) * 0.6)), 100)
            if D + E + F > C:
                F = 0
            else:
                loc = rng.choice(["On site", "On site", "Off site — bonded warehouse, approved in writing",
                                  "Off site — supplier yard, not approved"])
        lines.append([str(k + 1), SOV[k % len(SOV)], C, D, E, F, loc, True])
    for j in range(rng.randint(1, 2)):
        C = round_to(rng.uniform(5_000, 45_000), 100)
        lines.append([str(len(lines) + 1), f"PCO-{j + 4:02d} proposed change (unsigned)", C, 0,
                      round_to(C * rng.uniform(0.3, 1.0), 100), 0, "—", False])
    if stored_rule == "onsite_or_approved" and not any("not approved" in l[6] for l in lines):
        raise Retry
    printed = {l[0]: (l[3] + l[4] + l[5], l[2] - l[3] - l[4] - l[5]) for l in lines}
    errors = rng.sample([l[0] for l in lines if l[7]], rng.randint(2, 3))
    for item in errors:
        G, H = printed[item]
        delta = round_to(rng.uniform(1_000, 20_000), 100)
        printed[item] = (G + delta, H - delta) if rng.random() < .6 else (G, H + delta)
    ok = [l for l in lines if l[7]]
    payable_F = lambda l: l[5] if stored_rule == "all" or "not approved" not in l[6] else 0
    sumC = sum(l[2] for l in ok)
    sumDE = sum(l[3] + l[4] for l in ok)
    sumF = sum(payable_F(l) for l in ok)
    pct = (sumDE + sumF) / sumC
    if scheme == "step" and abs(pct - 0.5) < 0.03:
        raise Retry
    if scheme == "step":
        ret = (0.05 if pct > 0.5 else 0.10) * sumDE + 0.10 * sumF
        ret_clause = ("§9.4 Retainage. Contractor retains ten percent (10%) of the value of work completed and of "
                      "materials stored. Once the Work is more than fifty percent (50%) complete, measured as the value "
                      "of work completed plus payable stored materials divided by the Subcontract Sum, retainage on work "
                      "completed is five percent (5%) for the whole Subcontract; retainage on stored materials remains 10%.")
    elif scheme == "flat5":
        ret = 0.05 * (sumDE + sumF)
        ret_clause = ("§9.4 Retainage. Contractor retains five percent (5%) of each payment for work completed and "
                      "materials stored, without reduction until final completion.")
    else:
        ret = 0.10 * sumDE
        ret_clause = ("§9.4 Retainage. Contractor retains ten percent (10%) of the value of work completed. No retainage "
                      "is held on payable stored materials.")
    stored_clause = ("§9.5 Stored materials. Materials stored on or off site are payable when supported by invoices."
                     if stored_rule == "all" else
                     "§9.5 Stored materials. Materials stored on site are payable. Materials stored off site are payable "
                     "only if stored in a bonded warehouse and approved in writing by the Contractor; otherwise they are "
                     "not payable on this application (they stay on the continuation sheet but are excluded from "
                     "payment, percent complete and retainage).")
    prev_cert = round(sum(l[3] for l in ok) * 0.9)
    earned = sumDE + sumF
    due = earned - ret - prev_cert
    clauses = [
        "§2.1 Subcontract Sum. The Subcontract Sum is the total of the scheduled values of the continuation sheet, "
        "adjusted only by executed change orders.",
        "§9.2 Changes. No payment is due for changed work until the change order is executed by both parties; "
        "unsigned or proposed changes are excluded from the Subcontract Sum and from every payment total.",
        "§9.3 Review. Contractor checks the continuation sheet arithmetic. Column G must equal D + E + F and column H "
        "must equal C − G; lines that do not are reported and corrected to G = D + E + F before any total is taken.",
        ret_clause, stored_clause,
        "§9.6 Amount due. Amount due = value of work completed plus payable stored materials, less retainage, less "
        "previous certificates for payment.",
    ]
    rows = "\n".join(f"| {it} | {desc} | {money(C)} | {money(D)} | {money(E)} | {money(F)} | {loc} | "
                     f"{money(printed[it][0])} | {money(printed[it][1])} |" for it, desc, C, D, E, F, loc, _ in lines)
    fields = {"error_lines": SET, "excluded_lines": SET, "payable_completed_and_stored": number(0.001),
              "retainage": number(0.001), "amount_due": number(0.001)}
    prompt = (
        f"Certify this subcontractor pay application for {pick(rng, JOB_NAMES)} under the payment terms of the "
        "subcontract below. Previous certificates for payment total " + money(prev_cert) + ".\n\n"
        + excerpt(rng, "Subcontract agreement", clauses) + "\n\n"
        "| Item | Description | C scheduled value | D previous | E this period | F stored | Stored location | "
        "G (printed) | H (printed) |\n|---|---|---|---|---|---|---|---|---|\n" + rows + "\n\n"
        "Give the item numbers (as strings, e.g. \"7\") of lines with arithmetic errors and of lines excluded under the "
        "subcontract, the value of work completed plus payable stored materials, the retainage, and the amount due.\n"
        + answer_keys_line(fields))
    return Task(f"z-paycon-{i:04d}", "finance", "pay_app_contract", "Pay application under the subcontract's terms",
                EXTREME, prompt, {"error_lines": sorted(errors, key=int),
                                  "excluded_lines": [l[0] for l in lines if not l[7]],
                                  "payable_completed_and_stored": earned, "retainage": round(ret, 2),
                                  "amount_due": round(due, 2)}, fields,
                {"retainage_scheme": scheme, "stored_rule": stored_rule, "hidden_rules": True})


# ---------------------------------------------------------------- time extension and LDs under contract terms

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@_retrying
def delay_contract(rng: random.Random, i: int) -> Task:
    ntp = dt.date(2025, 4, 1) + dt.timedelta(days=rng.randint(0, 120))
    original = ntp + dt.timedelta(days=rng.choice([360, 420, 480]))
    contract_sum = round_to(rng.uniform(8_000_000, 40_000_000), 10_000)
    notice_days = rng.choice([7, 10, 14, 21])
    concurrency = rng.choice(["excusable", "contractor_bears"])
    ld_rate = rng.choice([2_500, 3_500, 5_000, 7_500])
    cap_pct = rng.choice([0.005, 0.01, 0.02, 0.05])
    gc_rate = rng.choice([1_850, 2_400, 3_100])
    # owner and contractor events (critical ones only listed here; non-critical carry no time)
    events = []
    for k in range(rng.randint(5, 8)):
        who = rng.choices(["Owner", "Contractor"], weights=[3, 2])[0]
        s = ntp + dt.timedelta(days=rng.randint(30, 300))
        e = s + dt.timedelta(days=rng.randint(4, 35) - 1)
        notice = s + dt.timedelta(days=rng.choice([1, 3, 5, 6, 8, 9, 12, 13, 15, 20, 22, 30]))
        events.append([f"D{k + 1}", who, s, e, rng.random() < .85, notice])
    events.sort(key=lambda ev: ev[2])
    for k, ev in enumerate(events):
        ev[0] = f"D{k + 1}"
    counted = [ev for ev in events if ev[4] and (ev[1] == "Contractor" or (ev[5] - ev[2]).days <= notice_days)]
    days: dict[dt.date, set] = {}
    for _, who, s, e, *_ in counted:
        d = s
        while d <= e:
            days.setdefault(d, set()).add(who)
            d += dt.timedelta(days=1)
    owner_only = sum(1 for w in days.values() if w == {"Owner"})
    concurrent = sum(1 for w in days.values() if w == {"Owner", "Contractor"})
    # weather: a log of critical weather days by month vs the contract's anticipated days
    months = sorted({(d.year, d.month) for d in (ntp + dt.timedelta(days=k) for k in range(30, 330, 30))})
    rng.shuffle(months)
    months = sorted(months[:rng.randint(4, 6)])
    anticipated = {m: rng.randint(2, 7) for m in range(1, 13)}
    weather = {(y, m): anticipated[m] + rng.randint(-2, 5) for y, m in months}
    weather_excess = sum(max(0, n - anticipated[m]) for (y, m), n in weather.items())
    ext = owner_only + (concurrent if concurrency == "excusable" else 0) + weather_excess
    extended = original + dt.timedelta(days=ext)
    actual = extended + dt.timedelta(days=rng.randint(-10, 120))
    ld_days = max(0, (actual - extended).days)
    ld = min(ld_days * ld_rate, cap_pct * contract_sum)
    comp_amount = owner_only * gc_rate
    if ext == 0 or owner_only == 0 or ld_days == 0:
        raise Retry
    conc_clause = ("§8.5 Concurrent delay. Where Owner-caused and Contractor-caused delays occur on the same day, the "
                   "day is excusable but not compensable." if concurrency == "excusable" else
                   "§8.5 Concurrent delay. Where Owner-caused and Contractor-caused delays occur on the same day, the "
                   "Contractor bears that day: it is neither excusable nor compensable.")
    clauses = [
        f"§2.1 Contract Sum. The Contract Sum is {money(contract_sum)}.",
        f"§3.2 Contract Time. Substantial Completion shall be achieved by {original.isoformat()}.",
        f"§8.2 Delay events. Only delays to activities on the critical path entitle the Contractor to additional time.",
        f"§8.3 Notice. The Contractor shall give written notice of an Owner-caused delay within {notice_days} calendar "
        "days after the delay begins; a delay without timely notice is waived in full.",
        "§8.4 Weather. Adverse weather days on critical work are excusable, not compensable, only to the extent that in "
        "a calendar month they exceed the anticipated adverse weather days in Exhibit W for that month.",
        conc_clause,
        f"§8.6 Compensation. For each day that is excusable and compensable (Owner-caused, not concurrent) the Owner "
        f"pays extended general conditions of {money(gc_rate)} per day.",
        f"§8.8 Liquidated damages. For each calendar day after the Contract Time, as extended, until Substantial "
        f"Completion, the Contractor pays {money(ld_rate)} per day, limited in total to {cap_pct * 100:g}% of the Contract Sum.",
    ]
    exhibit = "Exhibit W — anticipated adverse weather days: " + ", ".join(
        f"{MONTHS[m - 1]} {anticipated[m]}" for m in range(1, 13)) + "."
    erows = "\n".join(f"| {e} | {who} | {s.isoformat()} | {f.isoformat()} | {'Yes' if crit else 'No'} | "
                      f"{notice.isoformat()} |" for e, who, s, f, crit, notice in events)
    wrows = "\n".join(f"| {MONTHS[m - 1]} {y} | {n} |" for (y, m), n in weather.items())
    fields = {"extension_days": INTEGER, "extended_completion_date": DATE, "compensable_amount": number(0.0001),
              "liquidated_damages": number(0.0001)}
    prompt = (
        "Determine the time extension, the compensation owed for delay, and the liquidated damages, applying the contract "
        f"below. Actual Substantial Completion was {actual.isoformat()}.\n\n"
        + excerpt(rng, "Owner–Contractor agreement", clauses, prime=True) + "\n" + exhibit + "\n\n"
        "Delay log (dates inclusive, calendar days):\n\n| Delay | Caused by | Start | End | Critical path | Written notice |\n"
        "|---|---|---|---|---|---|\n" + erows + "\n\nAdverse weather days recorded on critical work (none fall on a "
        "logged delay day):\n\n| Month | Weather days |\n|---|---|\n" + wrows + "\n\n"
        "Count each calendar day once. Give the extension in days, the extended completion date, the compensable amount, "
        "and the liquidated damages.\n" + answer_keys_line(fields))
    return Task(f"z-delcon-{i:04d}", "contracts", "delay_contract", "Delay entitlement under the contract's terms",
                EXTREME, prompt, {"extension_days": ext, "extended_completion_date": extended.isoformat(),
                                  "compensable_amount": comp_amount, "liquidated_damages": round(ld, 2)}, fields,
                {"notice_days": notice_days, "concurrency": concurrency, "hidden_rules": True})


# ---------------------------------------------------------------- chained: takeoff → estimate → bid → schedule → cash

def chain_values(p: dict, overrides: dict | None = None) -> dict:
    """Every stage of the chained task from its parameters. `overrides` replaces a stage's value before the later
    stages use it (e.g. a model's own concrete quantity), which separates first errors from carried errors."""
    o = overrides or {}
    out = {}
    slab = p["L"] * p["W"] * p["slab_in"] / 12
    footing = 2 * (p["L"] + p["W"]) * p["ftg_w"] * p["ftg_d"]
    pads = p["pads"] * p["pad"] ** 2 * p["pad_d"]
    out["concrete_order_cy"] = o.get("concrete_order_cy",
                                     math.ceil((slab + footing + pads) / 27 * (1 + p["waste"]) * 2 - 1e-9) / 2)
    cy = out["concrete_order_cy"]
    forms_sf = 2 * 2 * (p["L"] + p["W"]) * p["ftg_d"] + p["pads"] * 4 * p["pad"] * p["pad_d"]
    labor_h = cy / p["cy_per_crew_hour"]
    out["direct_cost"] = o.get("direct_cost", round(
        cy * p["concrete_rate"] + cy * p["rebar_lb_per_cy"] * p["rebar_rate"] + forms_sf * p["form_rate"]
        + labor_h * p["crew_rate"], 2))
    sub = out["direct_cost"] * (1 + p["gc"])
    sub *= 1 + p["oh"]
    sub *= 1 + p["profit"]
    out["bid_price"] = o.get("bid_price", round(sub * (1 + p["bond"]), 2))
    pour_days = math.ceil(cy / p["cy_per_day"] - 1e-9)
    out["duration_workdays"] = o.get("duration_workdays", p["form_days"] + pour_days + p["cure_days"] + p["strip_days"])
    months = math.ceil(out["duration_workdays"] / 20 - 1e-9)
    cum, worst = 0.0, 0.0
    cost_m = out["direct_cost"] / months
    bill_m = out["bid_price"] / months
    for m in range(1, months + 2):
        if m <= months:
            cum -= cost_m
        if 2 <= m <= months + 1:
            cum += bill_m * (1 - p["ret"])
        worst = min(worst, cum)
    out["peak_cash_deficit"] = round(worst, 2)
    return out


@_retrying
def chained_concrete(rng: random.Random, i: int) -> Task:
    p = {"L": rng.randint(80, 240), "W": rng.randint(60, 160), "slab_in": rng.choice([5, 6, 8]),
         "ftg_w": rng.choice([2, 2.5, 3]), "ftg_d": rng.choice([1, 1.5, 2]), "pads": rng.randint(6, 24),
         "pad": rng.choice([4, 5, 6]), "pad_d": rng.choice([1.5, 2]), "waste": rng.choice([0.03, 0.05, 0.07]),
         "concrete_rate": rng.choice([165, 182, 198, 215]), "rebar_lb_per_cy": rng.choice([80, 100, 120, 150]),
         "rebar_rate": rng.choice([1.05, 1.18, 1.32]), "form_rate": rng.choice([7.5, 9.25, 11.0]),
         "cy_per_crew_hour": rng.choice([4.0, 5.0, 6.5]), "crew_rate": rng.choice([410, 465, 520]),
         "gc": rng.choice([0.06, 0.08, 0.10]), "oh": rng.choice([0.05, 0.07]), "profit": rng.choice([0.06, 0.08, 0.10]),
         "bond": rng.choice([0.008, 0.012]), "cy_per_day": rng.choice([60, 80, 100, 120]),
         "form_days": rng.randint(8, 20), "cure_days": rng.choice([7, 10, 14]), "strip_days": rng.randint(3, 6),
         "ret": rng.choice([0.05, 0.10])}
    v = chain_values(p)
    raw = (p["L"] * p["W"] * p["slab_in"] / 12 + 2 * (p["L"] + p["W"]) * p["ftg_w"] * p["ftg_d"]
           + p["pads"] * p["pad"] ** 2 * p["pad_d"]) / 27 * (1 + p["waste"]) * 2
    pours = v["concrete_order_cy"] / p["cy_per_day"]
    if raw - math.floor(raw) < 0.02 or pours - math.floor(pours) < 0.02 or v["duration_workdays"] % 20 == 0:
        raise Retry                                          # keep every rounding step away from a knife edge
    fields = {"concrete_order_cy": number(0.0001), "direct_cost": number(0.002), "bid_price": number(0.002),
              "duration_workdays": INTEGER, "peak_cash_deficit": number(0.002)}
    prompt = (
        f"Carry this concrete foundation package for {pick(rng, JOB_NAMES)} from takeoff to cash flow. Each step uses "
        "your result from the step before.\n\n"
        f"1. Takeoff. Building footprint {p['L']} ft × {p['W']} ft. Slab on grade {p['slab_in']} in thick over the whole "
        f"footprint. Continuous perimeter footing {p['ftg_w']:g} ft wide × {p['ftg_d']:g} ft deep along the full "
        f"perimeter (ignore corner overlap). {p['pads']} column pads, each {p['pad']} ft × {p['pad']} ft × "
        f"{p['pad_d']:g} ft deep. Add {p['waste']:.0%} waste to the total and order in whole half-yards (round up to the "
        "next 0.5 CY). → concrete_order_cy\n"
        f"2. Estimate (use the ordered CY): concrete ${p['concrete_rate']}/CY; rebar {p['rebar_lb_per_cy']} lb per CY at "
        f"${p['rebar_rate']:.2f}/lb; formwork on both sides of the perimeter footing for its full depth and on all four "
        f"sides of each pad for its full depth at ${p['form_rate']:.2f} per sq ft of contact area; placing crew "
        f"${p['crew_rate']}/hour at {p['cy_per_crew_hour']:g} CY per crew-hour. → direct_cost\n"
        f"3. Bid: add general conditions {p['gc']:.0%} on the direct cost, then overhead {p['oh']:.0%} on that "
        f"subtotal, then profit {p['profit']:.0%} on that subtotal, then bond {p['bond']:.1%} on that total. → bid_price\n"
        f"4. Schedule (working days, one sequence): forms {p['form_days']} days, then pours at {p['cy_per_day']} CY per "
        f"day (whole days, round up), then cure {p['cure_days']} days, then strip and backfill {p['strip_days']} days. "
        "→ duration_workdays\n"
        "5. Cash flow: months of 20 working days (round the duration up to whole months). Direct cost is spent evenly "
        "over those months and paid in the month spent. The bid price is billed evenly at the end of each month, the "
        f"owner withholds {p['ret']:.0%} retainage and pays the rest one month later (retainage is paid after the "
        "period studied). Cash position starts at 0; give the most negative month-end cumulative position. "
        "→ peak_cash_deficit\n\n" + answer_keys_line(fields))
    return Task(f"z-chain-{i:04d}", "estimating", "chained_concrete", "Takeoff to cash flow, chained", EXTREME, prompt,
                v, fields, {"params": p, "chained": True})
