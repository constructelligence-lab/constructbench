"""Scheduling: network logic, float, delay impact, look-ahead windows and schedule quality checks.

Every family builds one random finish-to-start network with `network()` and computes its answers with the
same forward/backward pass, so float, critical path and delay impact always agree with each other.
"""
from __future__ import annotations

import datetime as dt
import random

from ..task import Task, number, INTEGER, TEXT, SET, answer_keys_line
from .common import pick

NAMES = ["Mobilize", "Excavate", "Footings", "Foundation walls", "Underground MEP", "Slab on grade", "Steel erection",
         "Deck & pour", "Roofing", "Exterior envelope", "MEP rough-in", "Framing", "Drywall", "Finishes", "Commissioning"]


def network(rng: random.Random, n_min: int = 7, n_max: int = 11):
    n = rng.randint(n_min, n_max)
    ids = [chr(ord("A") + k) for k in range(n)]
    dur = {a: rng.randint(2, 15) for a in ids}
    preds = {ids[0]: []}
    for k in range(1, n):
        cands = ids[max(0, k - 3):k]
        m = 1 if k < 2 else rng.choice([1, 1, 2])
        preds[ids[k]] = sorted(rng.sample(cands, min(m, len(cands))))
    fed = {p for ps in preds.values() for p in ps}
    for a in ids[:-1]:
        if a not in fed:
            preds[ids[-1]] = sorted(set(preds[ids[-1]]) | {a})
    return ids, dur, preds


def cpm(ids, dur, preds):
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
    tf = {a: ls[a] - es[a] for a in ids}
    ff = {a: (min((es[s] for s in succ[a]), default=project) - ef[a]) for a in ids}
    return {"es": es, "ef": ef, "ls": ls, "lf": lf, "tf": tf, "ff": ff, "project": project, "succ": succ}


def _table(ids, dur, preds):
    return ("| ID | Activity | Duration | Predecessors |\n|---|---|---|---|\n" +
            "\n".join(f"| {a} | {NAMES[k % len(NAMES)]} | {dur[a]} | {', '.join(preds[a]) or '—'} |" for k, a in enumerate(ids)))


_RULES = ("Durations are working days; all logic is finish-to-start with no lags; the project starts on day 0 "
          "(an activity with no predecessors starts at 0).")


def critical_path(rng: random.Random, i: int) -> Task:
    ids, dur, preds = network(rng)
    c = cpm(ids, dur, preds)
    crit = [a for a in ids if c["tf"][a] == 0]
    fields = {"project_duration_days": INTEGER, "critical_activities": SET}
    prompt = (f"Schedule network for a building job. {_RULES}\n\n{_table(ids, dur, preds)}\n\n"
              "Give the project duration and the IDs of every activity with zero total float.\n" + answer_keys_line(fields))
    return Task(f"sch-cpm-{i:04d}", "scheduling", "critical_path", "Critical path", "hard", prompt,
                {"project_duration_days": c["project"], "critical_activities": crit}, fields)


def floats(rng: random.Random, i: int) -> Task:
    ids, dur, preds = network(rng)
    c = cpm(ids, dur, preds)
    noncrit = [a for a in ids if c["tf"][a] > 0] or ids
    a = pick(rng, noncrit)
    fields = {"early_start": INTEGER, "late_finish": INTEGER, "total_float": INTEGER, "free_float": INTEGER}
    prompt = (f"{_RULES}\n\n{_table(ids, dur, preds)}\n\n"
              f"For activity {a}, give its early start, late finish, total float and free float (free float = the earliest "
              "early start among its successors minus its early finish; for an activity with no successors, the project "
              "finish minus its early finish).\n" + answer_keys_line(fields))
    return Task(f"sch-float-{i:04d}", "scheduling", "float", "Total and free float", "hard", prompt,
                {"early_start": c["es"][a], "late_finish": c["lf"][a], "total_float": c["tf"][a], "free_float": c["ff"][a]},
                fields, {"activity": a})


def delay_impact(rng: random.Random, i: int) -> Task:
    ids, dur, preds = network(rng)
    c = cpm(ids, dur, preds)
    a = pick(rng, ids[1:-1])
    delay = rng.randint(2, 12)
    dur2 = dict(dur); dur2[a] += delay
    c2 = cpm(ids, dur2, preds)
    crit2 = [x for x in ids if c2["tf"][x] == 0]
    fields = {"original_finish": INTEGER, "new_finish": INTEGER, "project_delay_days": INTEGER, "critical_after": SET}
    prompt = (f"{_RULES}\n\n{_table(ids, dur, preds)}\n\n"
              f"Activity {a} is delayed: its duration grows by {delay} working days and nothing else changes. Give the original "
              "project finish, the new finish, the delay to the project, and the critical activities (zero total float) "
              "after the delay.\n" + answer_keys_line(fields))
    return Task(f"sch-delay-{i:04d}", "scheduling", "delay_impact", "Delay impact on the finish", "hard", prompt,
                {"original_finish": c["project"], "new_finish": c2["project"], "project_delay_days": c2["project"] - c["project"],
                 "critical_after": crit2}, fields, {"activity": a, "delay": delay})


def lookahead(rng: random.Random, i: int) -> Task:
    today = dt.date(2026, 10, 5)                                   # a Monday
    rows = []
    for k in range(rng.randint(10, 16)):
        start = today + dt.timedelta(days=rng.randint(-20, 40))
        finish = start + dt.timedelta(days=rng.randint(1, 30))
        rows.append((f"{k + 101}", NAMES[k % len(NAMES)] + (f" L{rng.randint(1, 6)}" if rng.random() < .5 else ""), start, finish))
    end = today + dt.timedelta(days=20)                            # three weeks: Mon 10/5 → Sun 10/25
    starting = [r[0] for r in rows if today <= r[2] <= end]
    active = [r[0] for r in rows if r[2] <= end and r[3] >= today]
    if not starting:
        return lookahead(rng, i)
    table = "\n".join(f"| {r[0]} | {r[1]} | {r[2]:%m/%d/%Y} | {r[3]:%m/%d/%Y} |" for r in rows)
    fields = {"starting_in_window": SET, "active_in_window": SET}
    prompt = (f"Build a three-week look-ahead for the Monday {today:%m/%d/%Y} coordination meeting: the window is "
              f"{today:%m/%d/%Y} through {end:%m/%d/%Y}, both inclusive.\n\n| ID | Activity | Start | Finish |\n|---|---|---|---|\n"
              + table + "\n\nList the activities that START inside the window, and every activity ACTIVE at any point in the "
              "window (it starts on or before the window's last day and finishes on or after its first day).\n" + answer_keys_line(fields))
    return Task(f"sch-look-{i:04d}", "scheduling", "lookahead", "Three-week look-ahead", "easy", prompt,
                {"starting_in_window": starting, "active_in_window": active}, fields)


def health(rng: random.Random, i: int) -> Task:
    """Schedule quality checks in the spirit of the DCMA 14-point assessment, on stated rules."""
    n = rng.randint(12, 20)
    ids = [f"A{100 + k * 10}" for k in range(n)]
    rows, no_pred, no_succ, neg_lag, hard, long_dur = [], [], [], [], [], []
    succ_count = {a: 0 for a in ids}
    for k, a in enumerate(ids):
        d = rng.randint(1, 60)
        preds = []
        if k > 0 and rng.random() > .18:
            p = pick(rng, ids[max(0, k - 4):k])
            lag = rng.choice([0, 0, 0, 0, 2, 5, -3])
            preds.append((p, lag))
            succ_count[p] += 1
            if lag < 0:
                neg_lag.append(a)
        constraint = rng.choice(["", "", "", "", "Must finish on", "Start no earlier than"])
        if constraint == "Must finish on":
            hard.append(a)
        if d > 44:
            long_dur.append(a)
        rows.append((a, d, preds, constraint))
    for a, _, preds, _ in rows:
        if not preds and a != ids[0]:
            no_pred.append(a)
    for a in ids[:-1]:
        if succ_count[a] == 0:
            no_succ.append(a)
    fmt = lambda ps: ", ".join(f"{p}{'' if lag == 0 else f' FS{lag:+d}'}" for p, lag in ps) or "—"
    table = "\n".join(f"| {a} | {d} | {fmt(ps)} | {c or '—'} |" for a, d, ps, c in rows)
    fields = {"missing_predecessor": SET, "missing_successor": SET, "negative_lag": SET, "hard_constraints": SET,
              "over_44_days": SET}
    prompt = (f"Run these schedule quality checks on the activity list below ({ids[0]} is the project start milestone and "
              f"{ids[-1]} the finish milestone, which are exempt from the missing-predecessor and missing-successor checks "
              "respectively). Logic is finish-to-start with the lag shown.\n"
              "- missing predecessor: no predecessor listed\n- missing successor: no activity lists it as a predecessor\n"
              "- negative lag: has a predecessor relationship with a negative lag\n- hard constraint: \"Must finish on\" "
              "(\"Start no earlier than\" is a soft constraint and does not count)\n- high duration: more than 44 working days\n\n"
              "| ID | Duration | Predecessors | Constraint |\n|---|---|---|---|\n" + table + "\n" + answer_keys_line(fields))
    return Task(f"sch-health-{i:04d}", "scheduling", "schedule_health", "Schedule quality checks", "medium", prompt,
                {"missing_predecessor": no_pred, "missing_successor": no_succ, "negative_lag": neg_lag,
                 "hard_constraints": hard, "over_44_days": long_dur}, fields)
