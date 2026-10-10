"""Quality control, contracts & claims, and survey leveling.

The checks a QC manager, a project manager reading the contract, and a field engineer with a level do by hand —
each with the rule stated in the prompt, so a task has one right answer and the score is the arithmetic and the
reading of the rule, not recall of a code edition.
"""
from __future__ import annotations

import datetime as dt
import math
import random

from ..task import Task, number, INTEGER, TEXT, DATE, LIST, answer_keys_line
from .common import job_no, money, pick


# ── Quality control ──────────────────────────────────────────────────────────────────────────────────────

def concrete_acceptance(rng: random.Random, i: int) -> Task:
    """ACI 318-style acceptance: 3-test running averages >= f'c, and no single test below the individual limit."""
    fc = pick(rng, [3000, 4000, 4500, 5000, 6000, 7000])
    n = rng.randint(6, 10)
    tests = []
    for _ in range(n):
        centre = fc * rng.uniform(1.0, 1.22)
        if rng.random() < 0.08:                                   # an occasional weak load
            centre = fc * rng.uniform(0.78, 0.98)
        a = int(round(centre + rng.uniform(-250, 250), -1))
        b = int(round(centre + rng.uniform(-250, 250), -1))
        tests.append((a, b))
    strengths = [(a + b) / 2 for a, b in tests]
    limit = fc - 500 if fc <= 5000 else 0.90 * fc
    windows = [sum(strengths[k:k + 3]) / 3 for k in range(n - 2)]
    low_windows = sum(1 for w in windows if w < fc)
    low_tests = sum(1 for s in strengths if s < limit)
    rows = "\n".join(f"| {k + 1} | {a:,} | {b:,} |" for k, (a, b) in enumerate(tests))
    fields = {"lowest_test_psi": number(abs_tol=0.5), "lowest_three_test_average_psi": number(abs_tol=0.5),
              "failing_three_test_averages": INTEGER, "tests_below_individual_limit": INTEGER, "acceptable": TEXT}
    prompt = (f"Concrete for a slab on {job_no(rng)} is specified at f'c = {fc:,} psi. Each strength test is the average of the two "
              f"28-day cylinders broken from one sample, in placement order:\n\n| Test | Cylinder A (psi) | Cylinder B (psi) |\n|---|---|---|\n"
              f"{rows}\n\nAcceptance rule: (1) every average of three consecutive strength tests must be at least f'c; and (2) no "
              f"single strength test may fall more than 500 psi below f'c when f'c is 5,000 psi or less, or below 0.90 × f'c when f'c "
              "is more than 5,000 psi. Give the lowest strength test, the lowest three-consecutive-test average, how many "
              "three-test averages are below f'c, how many single tests are below the individual limit, and whether the concrete "
              "is \"acceptable\" or \"not acceptable\" (both rules must hold).\n" + answer_keys_line(fields))
    return Task(f"qc-conc-{i:04d}", "quality", "concrete_acceptance", "Concrete strength acceptance", "medium", prompt,
                {"lowest_test_psi": min(strengths), "lowest_three_test_average_psi": round(min(windows), 2),
                 "failing_three_test_averages": low_windows, "tests_below_individual_limit": low_tests,
                 "acceptable": "acceptable" if low_windows == 0 and low_tests == 0 else "not acceptable"}, fields)


def compaction(rng: random.Random, i: int) -> Task:
    """Nuclear-gauge field tests against a Proctor maximum: relative compaction and the moisture window."""
    mdd = round(rng.uniform(112, 132), 1)              # pcf
    opt = round(rng.uniform(8, 14), 1)                 # %
    spec = pick(rng, [90, 92, 95, 98])
    band = pick(rng, [2, 3])
    n = rng.randint(5, 8)
    rows, failing, rcs = [], [], []
    for k in range(n):
        w = round(opt + rng.uniform(-band - 1.5, band + 1.2), 1)
        target_rc = rng.uniform(spec - 4, spec + 5)
        dry = mdd * target_rc / 100
        wet = round(dry * (1 + w / 100), 1)
        dry = wet / (1 + w / 100)
        rc = dry / mdd * 100
        rcs.append(rc)
        tid = f"T{k + 1}"
        rows.append(f"| {tid} | {wet} | {w} |")
        if rc < spec or abs(w - opt) > band:
            failing.append(tid)
    fields = {"failing_tests": LIST, "percent_passing": number(abs_tol=0.05), "average_relative_compaction_pct": number(abs_tol=0.05)}
    prompt = (f"Structural fill under a footing is specified at {spec}% relative compaction (field dry density ÷ laboratory maximum dry "
              f"density) with moisture within ±{band} percentage points of optimum. The modified Proctor gives a maximum dry density of "
              f"{mdd} pcf at {opt}% optimum moisture. Field tests:\n\n| Test | Wet density (pcf) | Moisture (%) |\n|---|---|---|\n"
              + "\n".join(rows) + "\n\nDry density = wet density ÷ (1 + moisture/100). A test passes only if both the compaction and "
              "the moisture requirement are met (boundaries pass). Give the failing test ids in test order, the percent of tests "
              "passing, and the average relative compaction of all tests (percent).\n" + answer_keys_line(fields))
    return Task(f"qc-comp-{i:04d}", "quality", "compaction", "Field compaction tests", "medium", prompt,
                {"failing_tests": failing, "percent_passing": round((n - len(failing)) / n * 100, 4),
                 "average_relative_compaction_pct": round(sum(rcs) / n, 4)}, fields)


# ── Civil: survey leveling ───────────────────────────────────────────────────────────────────────────────

def leveling(rng: random.Random, i: int) -> Task:
    """Differential leveling loop: HI = elevation + BS, next elevation = HI − FS, closed on the starting benchmark."""
    bm = round(rng.uniform(95, 480), 3)
    stations = ["BM-1"] + [f"TP{k}" for k in range(1, rng.randint(3, 5))] + ["FF-A"] + [f"TP{k}" for k in range(9, 9 + rng.randint(1, 2))] + ["BM-1"]
    elev = bm
    rows, elevations = [], {}
    true = [bm]
    for _ in stations[1:-1]:
        true.append(true[-1] + rng.uniform(-3.2, 3.2))
    true.append(bm)
    error = rng.choice([-1, 1]) * rng.uniform(0.002, 0.06)        # the loop's misclosure, spread over the readings
    legs = len(stations) - 1
    for k in range(legs):
        bs = round(rng.uniform(3.0, 9.5), 3)
        fs = round(bs - (true[k + 1] - true[k]) - error / legs, 3)
        hi = elev + bs
        elev = round(hi - fs, 3)
        rows.append((stations[k], bs, stations[k + 1], fs))
        elevations[stations[k + 1]] = elev
    misclosure = round(elev - bm, 3)
    loop_ft = rng.randint(1200, 9000)
    c = pick(rng, [0.035, 0.05])
    allowable = c * math.sqrt(loop_ft / 5280)
    table = "\n".join(f"| {a} | {b:.3f} | {c_} | {d:.3f} |" for a, b, c_, d in rows)
    fields = {"ff_a_elevation_ft": number(abs_tol=0.0015), "misclosure_ft": number(abs_tol=0.0015),
              "allowable_ft": number(abs_tol=0.0005), "within_tolerance": TEXT}
    prompt = (f"A level loop starts and ends on BM-1 (elevation {bm:.3f} ft) and sets finished-floor control point FF-A. Each line "
              f"is one instrument setup: a backsight (BS) on the first point and a foresight (FS) on the next.\n\n| From | BS (ft) | To | FS (ft) |\n"
              f"|---|---|---|---|\n{table}\n\nHeight of instrument = elevation + BS; next elevation = height of instrument − FS. Carry "
              "unadjusted elevations around the loop (no adjustment). Give FF-A's elevation, the misclosure (computed closing elevation "
              f"of BM-1 − its known elevation), the allowable misclosure = {c} × √(loop length in miles) with the loop {loop_ft:,} ft "
              "long, and whether |misclosure| is within it (\"yes\"/\"no\").\n" + answer_keys_line(fields))
    return Task(f"civ-level-{i:04d}", "civil", "leveling", "Differential leveling loop", "medium", prompt,
                {"ff_a_elevation_ft": elevations["FF-A"], "misclosure_ft": misclosure, "allowable_ft": round(allowable, 4),
                 "within_tolerance": "yes" if abs(misclosure) <= allowable else "no"}, fields)


# ── Contracts & claims ───────────────────────────────────────────────────────────────────────────────────

def _d(x: dt.date) -> str:
    return x.isoformat()


def delay_claim(rng: random.Random, i: int) -> Task:
    """Time extension, compensable days (concurrency removes compensation), liquidated damages with a cap."""
    contract = round(rng.uniform(2_000_000, 40_000_000), -3)
    start = dt.date(2025, rng.randint(1, 12), rng.randint(1, 28))
    duration = rng.randint(240, 600)
    original = start + dt.timedelta(days=duration)
    events = []
    for k in range(rng.randint(3, 5)):
        cause = pick(rng, ["owner", "owner", "weather", "contractor"])
        days = rng.randint(4, 35)
        concurrent = rng.randint(0, days // 2) if cause == "owner" and rng.random() < 0.5 else 0
        events.append((k + 1, cause, days, concurrent))
    ext = sum(d for _, c, d, _ in events if c in ("owner", "weather"))
    comp = sum(d - cc for _, c, d, cc in events if c == "owner")
    late_actual = rng.randint(-5, 70)
    actual = original + dt.timedelta(days=ext + late_actual)
    days_late = max(0, (actual - (original + dt.timedelta(days=ext))).days)
    ld_rate = pick(rng, [500, 1000, 1500, 2500, 5000])
    cap_pct = pick(rng, [5, 10])
    ld = min(days_late * ld_rate, contract * cap_pct / 100)
    gc_day = round(rng.uniform(1200, 6500), -1)
    damages = comp * gc_day
    labels = {"owner": "owner (late design change / access)", "weather": "unusually severe weather", "contractor": "contractor (late submittals)"}
    rows = "\n".join(f"| {k} | {labels[c]} | {d} | {cc if c == 'owner' else '—'} |" for k, c, d, cc in events)
    fields = {"extension_days": INTEGER, "compensable_days": INTEGER, "days_late": INTEGER,
              "liquidated_damages": number(abs_tol=0.5), "delay_damages": number(abs_tol=0.5), "net_to_contractor": number(abs_tol=1)}
    prompt = (f"A {money(contract)} lump-sum contract started {_d(start)} with substantial completion due {_d(original)}. Liquidated damages "
              f"are {money(ld_rate)} per calendar day, capped at {cap_pct}% of the contract sum. Extended general conditions are "
              f"{money(gc_day)} per day. Delay events (all on the critical path, calendar days):\n\n| Event | Cause | Days | Of which concurrent "
              f"with contractor delay |\n|---|---|---|---|\n{rows}\n\nContract rules: owner delays and unusually severe weather are excusable "
              "(the completion date extends by their full days); only owner delays are compensable, and owner-delay days that were concurrent "
              "with a contractor delay are excusable but not compensable; contractor delays earn nothing. Substantial completion was actually "
              f"achieved on {_d(actual)}. Give the time extension, the compensable days, the days late against the extended date (0 if on "
              "time), the liquidated damages (after the cap), the contractor's delay damages (compensable days × extended general "
              "conditions), and the net to the contractor (delay damages − liquidated damages).\n" + answer_keys_line(fields))
    return Task(f"con-delay-{i:04d}", "contracts", "delay_claim", "Delay claim and liquidated damages", "hard", prompt,
                {"extension_days": ext, "compensable_days": comp, "days_late": days_late, "liquidated_damages": round(ld, 2),
                 "delay_damages": round(damages, 2), "net_to_contractor": round(damages - ld, 2)}, fields)


def _roll(x: dt.date) -> dt.date:
    """A deadline on a weekend moves to the following Monday."""
    return x + dt.timedelta(days=(7 - x.weekday()) % 7) if x.weekday() >= 5 else x


def notice_deadlines(rng: random.Random, i: int) -> Task:
    """Preliminary notice, lien recording, foreclosure and prompt-payment interest from rules stated in the prompt."""
    first = dt.date(2026, rng.randint(1, 9), rng.randint(1, 28))
    last = first + dt.timedelta(days=rng.randint(40, 220))
    pn_days, lien_days, suit_days = pick(rng, [20, 30, 45]), pick(rng, [60, 90, 120]), pick(rng, [90, 180, 365])
    pn = _roll(first + dt.timedelta(days=pn_days))
    lien = _roll(last + dt.timedelta(days=lien_days))
    recorded = lien - dt.timedelta(days=rng.randint(0, 25))
    suit = _roll(recorded + dt.timedelta(days=suit_days))
    invoice = round(rng.uniform(15_000, 480_000), 2)
    received = last - dt.timedelta(days=rng.randint(10, 35))
    pay_days = pick(rng, [30, 45])
    due = received + dt.timedelta(days=pay_days)
    paid = due + dt.timedelta(days=rng.randint(1, 75))
    late = (paid - due).days
    rate = pick(rng, [1.0, 1.5, 2.0])
    interest = invoice * rate / 100 * late / 30
    fields = {"preliminary_notice_deadline": DATE, "lien_recording_deadline": DATE, "foreclosure_deadline": DATE,
              "payment_due_date": DATE, "days_paid_late": INTEGER, "interest_due": number(abs_tol=0.01)}
    prompt = (f"{pick(rng, ['Voltline Electric', 'Northfield Plumbing', 'Summit Drywall & Acoustics', 'Keystone Roofing'])} first furnished labor "
              f"on {_d(first)} and last furnished on {_d(last)}. The statute (as stated here) requires: a preliminary notice within {pn_days} "
              f"days after first furnishing; a lien recorded within {lien_days} days after last furnishing; and a suit to foreclose within "
              f"{suit_days} days after the lien is recorded. Every period is calendar days counted from the day after the event, and a deadline "
              f"that falls on a Saturday or Sunday moves to the following Monday (ignore holidays). The lien was recorded on {_d(recorded)}.\n"
              f"Separately, its {money(invoice, True)} invoice was received on {_d(received)}; payment is due {pay_days} days after receipt "
              f"(no weekend adjustment) and was made on {_d(paid)}. Late payment bears simple interest of {rate}% per 30 days, prorated by day.\n"
              "Give the three statutory deadlines, the payment due date, the days paid late, and the interest due.\n" + answer_keys_line(fields))
    return Task(f"con-notice-{i:04d}", "contracts", "notice_deadlines", "Notice, lien and prompt-payment deadlines", "medium", prompt,
                {"preliminary_notice_deadline": _d(pn), "lien_recording_deadline": _d(lien), "foreclosure_deadline": _d(suit),
                 "payment_due_date": _d(due), "days_paid_late": late, "interest_due": round(interest, 2)}, fields)
