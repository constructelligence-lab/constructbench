"""Helpers the ci: agent preloads into every program it runs — standard construction calculations a small model gets
wrong by hand, done once and tested here.

Only `math` and `decimal` may be imported: this file's source is executed inside the agent's sandbox, ahead of the model's program.
Nothing here knows any task's answer; each helper is a textbook method (CPM forward/backward pass, time value of money).
"""
import math
from decimal import ROUND_HALF_UP, Decimal


def preds_of(value):
    """'B, D' / ['B','D'] / '—' / '' / None -> ['B', 'D'] or []."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip() not in ("", "—", "-", "–")]
    s = str(value).strip()
    if s in ("", "—", "-", "–", "none", "None"):
        return []
    return [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]


def cpm(activities, start=0):
    """Critical path method, finish-to-start with no lags.
    activities: list of dicts with 'id', 'duration' and 'preds' (list, or a string like 'B, D' or '—').
    Returns {'duration': project length, 'critical': [ids with zero total float, in input order],
             'by_id': {id: {'es','ef','ls','lf','tf','ff'}}}."""
    acts = {str(a["id"]): {"d": float(a["duration"]), "p": preds_of(a.get("preds"))} for a in activities}
    order, seen = [], set()

    def visit(i, stack=()):
        if i in seen:
            return
        if i in stack:
            raise ValueError("logic loop at " + i)
        for p in acts[i]["p"]:
            if p not in acts:
                raise KeyError("unknown predecessor " + p + " of " + i)
            visit(p, stack + (i,))
        seen.add(i)
        order.append(i)

    for i in acts:
        visit(i)
    es, ef = {}, {}
    for i in order:
        es[i] = max([ef[p] for p in acts[i]["p"]], default=start)
        ef[i] = es[i] + acts[i]["d"]
    finish = max(ef.values(), default=start)
    succ = {i: [j for j in acts if i in acts[j]["p"]] for i in acts}
    ls, lf = {}, {}
    for i in reversed(order):
        lf[i] = min([ls[s] for s in succ[i]], default=finish)
        ls[i] = lf[i] - acts[i]["d"]
    by_id = {}
    for i in acts:
        ff = min([es[s] for s in succ[i]], default=finish) - ef[i]
        by_id[i] = {"es": _n(es[i]), "ef": _n(ef[i]), "ls": _n(ls[i]), "lf": _n(lf[i]),
                    "tf": _n(ls[i] - es[i]), "ff": _n(ff)}
    return {"duration": _n(finish - start), "critical": [i for i in acts if abs(ls[i] - es[i]) < 1e-9],
            "by_id": by_id}


def _n(x):
    return int(x) if float(x).is_integer() else x


def pv(amount, rate, years):
    """Present value of one amount paid at the end of year `years` (rate as a fraction, 0.07 = 7%)."""
    return amount / (1 + rate) ** years


def pv_annuity(payment, rate, years):
    """Present value of `payment` at the end of each year for `years` years."""
    if rate == 0:
        return payment * years
    return payment * (1 - (1 + rate) ** -years) / rate


def npv(rate, cashflows):
    """cashflows[0] is now (year 0), cashflows[t] is the end of year t."""
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))


def irr(cashflows, lo=-0.99, hi=10.0):
    """Rate where npv is zero, by bisection (cashflows must change sign once)."""
    f_lo = npv(lo, cashflows)
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid, cashflows)
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


def round_half_up(x, places=0):
    """Rounds .5 away from zero (Python's round() goes to even: round(2.5) == 2)."""
    # Decimal(str(x)) rounds the number as written: 1.005 -> 1.01 (binary floats store it as 1.00499...).
    r = float(Decimal(str(x)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))
    return int(r) if places <= 0 else r


HELP = """Already defined for you (call them, do not re-implement):
- cpm(activities) — critical path, finish-to-start, no lags. activities = [{'id': 'A', 'duration': 10, 'preds': 'B, D'}, ...]
  ('preds' may be a list or a string; '—' means none). Returns {'duration': n, 'critical': [ids with zero total float],
  'by_id': {id: {'es','ef','ls','lf','tf','ff'}}}.
- pv(amount, rate, years), pv_annuity(payment, rate, years), npv(rate, cashflows_from_year_0), irr(cashflows)
  — rate as a fraction (7% -> 0.07); payments at the end of each year.
- round_half_up(x, places=0) — rounds .5 up (Python's round() rounds .5 to even)."""
