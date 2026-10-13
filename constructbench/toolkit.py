"""Helpers the ci: agent preloads into every program it runs — standard construction calculations a small model gets
wrong by hand, done once and tested here.

Only `math`, `re` and `decimal` may be imported: this file's source is executed inside the agent's sandbox, ahead of the model's program.
Nothing here knows any task's answer; each helper is a textbook method (CPM forward/backward pass, time value of money).
"""
import math
import re as _re
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


def _step_value(tok):
    tok = tok.strip()
    if tok in ("$", "*", ""):
        return None
    if tok.startswith("'") and tok.endswith("'"):
        return tok[1:-1].replace("''", "'")
    if tok.startswith(".") and tok.endswith(".") and len(tok) > 2:
        return tok[1:-1]                                    # enumeration: .ELEMENT. -> 'ELEMENT'
    if tok.startswith("#"):
        return tok                                          # reference kept as '#123'
    try:
        return float(tok) if any(c in tok for c in ".eE") else int(tok)
    except ValueError:
        return tok                                          # typed value such as IFCLABEL('x') stays as text


def step_args(s):
    """The attribute list of one STEP entity, 'a',#1,(#2,#3),$,.T.,1.5 -> ['a', '#1', ['#2', '#3'], None, 'T', 1.5]."""
    out, stack, tok, in_str, i = [], [], "", False, 0
    cur = out
    while i < len(s):
        ch = s[i]
        if in_str:
            tok += ch
            if ch == "'":
                if i + 1 < len(s) and s[i + 1] == "'":
                    tok += "'"; i += 1
                else:
                    in_str = False
        elif ch == "'":
            in_str, tok = True, tok + ch
        elif ch == "(" and tok.strip() == "":
            new = []
            cur.append(new); stack.append(cur); cur = new
        elif ch == "(":
            depth, j = 1, i + 1                             # a typed value like IFCLABEL('x'): keep it whole
            while j < len(s) and depth:
                depth += {"(": 1, ")": -1}.get(s[j], 0); j += 1
            tok += s[i:j]; i = j - 1
        elif ch == ")":
            if tok.strip():
                cur.append(_step_value(tok))
            tok = ""
            cur = stack.pop()
        elif ch == ",":
            if tok.strip():
                cur.append(_step_value(tok))
            elif s[i - 1] not in ")":
                cur.append(None)
            tok = ""
        else:
            tok += ch
        i += 1
    if tok.strip():
        cur.append(_step_value(tok))
    return out


def parse_step(text):
    """An IFC/STEP file (or excerpt) -> {'#123': {'type': 'IFCWALL', 'args': [...]}}. Lists come back as Python lists,
    references as '#n' strings, $ as None, enumerations without dots, numbers as numbers."""
    ents = {}
    for m in _re.finditer(r"(#\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*?)\)\s*;\s*(?=#\d+\s*=|$|ENDSEC)", text, _re.S):
        ents[m.group(1)] = {"type": m.group(2), "args": step_args(m.group(3))}
    return ents


def box_overlap(a, b):
    """Per-axis overlap of two boxes given as (x0, x1, y0, y1, z0, z1); a hard clash when all three are > 0."""
    return [min(a[1], b[1]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[2], b[2]), min(a[5], b[5]) - max(a[4], b[4])]


def box_gap(a, b):
    """Clear distance between two boxes (0 when they touch or overlap): √(gx² + gy² + gz²)."""
    g = [max(0, b[k] - a[k + 1], a[k] - b[k + 1]) for k in (0, 2, 4)]
    return math.sqrt(sum(v * v for v in g))


HELP = """Already defined for you (call them, do not re-implement):
- cpm(activities) — critical path, finish-to-start, no lags. activities = [{'id': 'A', 'duration': 10, 'preds': 'B, D'}, ...]
  ('preds' may be a list or a string; '—' means none). Returns {'duration': n, 'critical': [ids with zero total float],
  'by_id': {id: {'es','ef','ls','lf','tf','ff'}}}.
- pv(amount, rate, years), pv_annuity(payment, rate, years), npv(rate, cashflows_from_year_0), irr(cashflows)
  — rate as a fraction (7% -> 0.07); payments at the end of each year.
- round_half_up(x, places=0) — rounds .5 up (Python's round() rounds .5 to even).
- parse_step(text) — an IFC/STEP file -> {'#123': {'type': 'IFCWALL', 'args': [...]}}; references stay '#n' strings,
  lists are lists, $ is None, .ENUM. is 'ENUM'. Follow references through the dict.
- box_overlap(a, b) -> [ox, oy, oz] and box_gap(a, b) -> clear distance, boxes as (x0, x1, y0, y1, z0, z1)."""
