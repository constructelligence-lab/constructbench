"""Helpers the ci: agent preloads into every program it runs — standard construction calculations a small model gets
wrong by hand, done once and tested here.

Only `math`, `re`, `datetime` and `decimal` may be imported: this file's source is executed inside the agent's sandbox,
ahead of the model's program. Nothing here knows any task's answer; each helper is a textbook method (CPM forward/backward
pass, PDM relationships with lags, average-end-area earthwork, time value of money).
"""
import datetime as _dt
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


def _fraction(x):
    """A percentage given as 18 or 18.0 means 18%: anything above 1 is a percent, not a fraction."""
    x = float(x)
    return x / 100.0 if abs(x) > 1 else x


def _as_date(d):
    """A datetime.date, or a string date — 'YYYY-MM-DD' or 'MM/DD/YYYY' — as a date. Surrounding space is tolerated
    (models write ' 2026-08-24' often)."""
    if isinstance(d, _dt.date):
        return d
    s = str(d).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return _dt.datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    raise ValueError("not a date: " + repr(d))


def pdm(activities):
    """Precedence diagram with FS/SS/FF relationships and lags, in day numbers (EF = ES + duration; nothing starts
    before day 0 — an activity of duration d works days ES … EF−1).
    activities = [{'id': 'A010', 'duration': 6, 'preds': 'A020 FS+3, A010 SS+1'}, ...] — 'preds' may be the table
    string ('A020 FS' / 'A020' / '—') or a list. Returns {'duration': project length,
    'critical': [ids with zero total float, in input order], 'by_id': {id: {'es','ef','ls','lf','tf'}}}."""
    def parse(tok):
        m = _re.fullmatch(r"\s*([A-Za-z0-9_.\-]+)\s*(?:(FS|SS|FF)\s*)?(?:\+\s*(\d+))?\s*", str(tok))
        return (m.group(1), m.group(2) or "FS", float(m.group(3) or 0)) if m else (str(tok).strip(), "FS", 0.0)

    dur = {str(a["id"]): float(a["duration"]) for a in activities}
    rel = {str(a["id"]): [parse(t) for t in preds_of(a.get("preds"))] for a in activities}
    order, seen = [], set()

    def visit(i, stack=()):
        if i in seen:
            return
        if i in stack:
            raise ValueError("logic loop at " + i)
        for p, _, _ in rel[i]:
            if p not in dur:
                raise KeyError("unknown predecessor " + p + " of " + i)
            visit(p, stack + (i,))
        seen.add(i)
        order.append(i)

    for i in dur:
        visit(i)
    es, ef = {}, {}
    for i in order:
        bounds = [{"FS": ef[p] + lag, "SS": es[p] + lag, "FF": ef[p] + lag - dur[i]}[t] for p, t, lag in rel[i]]
        es[i] = max([0.0] + bounds)
        ef[i] = es[i] + dur[i]
    project = max(ef.values(), default=0.0)
    succ = {i: [] for i in dur}
    for i in dur:
        for p, t, lag in rel[i]:
            succ[p].append((i, t, lag))
    ls, lf = {}, {}
    for i in reversed(order):
        bounds = [{"FS": ls[s] - lag, "SS": ls[s] - lag + dur[i], "FF": lf[s] - lag}[t] for s, t, lag in succ[i]]
        lf[i] = min([project] + bounds)
        ls[i] = lf[i] - dur[i]
    return {"duration": _n(project), "critical": [i for i in dur if abs(ls[i] - es[i]) < 1e-9],
            "by_id": {i: {"es": _n(es[i]), "ef": _n(ef[i]), "ls": _n(ls[i]), "lf": _n(lf[i]),
                          "tf": _n(ls[i] - es[i])} for i in dur}}


def working_day_date(day0, k, holidays=(), weekdays=(0, 1, 2, 3, 4)):
    """The date of working day k, with day 0 the first working day on or after `day0` (so k=0 gives that date).
    day0 and each holiday may be a date or 'YYYY-MM-DD'; weekdays uses Python's numbers (Mon=0 … Sun=6, so Mon–Fri is
    the default). Holidays are skipped and are never counted as working days."""
    d, hol, k = _as_date(day0), {_as_date(h) for h in holidays}, int(k)
    while not (d.weekday() in weekdays and d not in hol):
        d += _dt.timedelta(days=1)
    seen = 0
    while seen < k:
        d += _dt.timedelta(days=1)
        if d.weekday() in weekdays and d not in hol:
            seen += 1
    return d


def station_label(feet):
    """1250 -> '12+50': how a station is printed on drawings (100 ft per unit before the '+', 2 digits after)."""
    f = int(round(float(feet)))
    return "%d+%02d" % (f // 100, f % 100)


def mass_haul(cut_areas, fill_areas, length, shrink, stations=None):
    """Average-end-area earthwork with shrinkage: each interval volume = (A1 + A2) / 2 × length ÷ 27. Cut is bank
    (bcy) and 1 bcy of cut makes (1 − shrink) ccy of fill. The mass ordinate starts at 0 on the first station and
    each next station adds that interval's cut × (1 − shrink) minus its fill, in station order.
    `shrink` may be a fraction (0.18) or a percent (18). Returns {'cut_bcy', 'fill_ccy', 'net_bcy', 'ordinates',
    'max_ordinate', 'max_index', 'max_station'} — max_ordinate is the PEAK of the ordinates, not the final one, and
    max_station is `stations[max_index]` when station labels are passed in."""
    s = _fraction(shrink)
    cut, fill = [float(a) for a in cut_areas], [float(a) for a in fill_areas]
    total_cut = total_fill = 0.0
    ords = [0.0]
    for k in range(len(cut) - 1):
        cv = (cut[k] + cut[k + 1]) / 2.0 * float(length) / 27.0
        fv = (fill[k] + fill[k + 1]) / 2.0 * float(length) / 27.0
        total_cut += cv
        total_fill += fv
        ords.append(ords[-1] + cv * (1 - s) - fv)
    top = max(range(len(ords)), key=lambda k: ords[k])
    return {"cut_bcy": _n(total_cut), "fill_ccy": _n(total_fill), "net_bcy": _n(ords[-1] / (1 - s)),
            "ordinates": [_n(o) for o in ords], "max_ordinate": _n(ords[top]), "max_index": top,
            "max_station": (stations[top] if stations else None)}


def manning_full(diameter_in, slope, n):
    """Full-flow capacity of a circular pipe, US units: Q = 1.49/n × A × R^(2/3) × S^(1/2), in cfs.
    diameter_in in inches, slope as a fraction (0.005 = 0.5%), n Manning's roughness (0.013 for concrete)."""
    d = float(diameter_in) / 12.0
    return 1.49 / float(n) * (math.pi * d * d / 4.0) * (d / 4.0) ** (2.0 / 3.0) * math.sqrt(float(slope))


def compound_markups(base, pcts):
    """Apply percentages to the running total in the order given: base × (1+p1) × (1+p2) …
    Each pct may be a fraction (0.08) or a percent (8). Markups are never added together first."""
    out = float(base)
    for p in pcts:
        out *= 1 + _fraction(p)
    return _n(out)


def evm(pv, ev, ac, bac):
    """Earned-value metrics: CPI = EV/AC, SPI = EV/PV, CV = EV − AC, SV = EV − PV, EAC = BAC/CPI, ETC = EAC − AC,
    TCPI = (BAC − EV)/(BAC − AC). Returns them as a dict."""
    cpi = ev / ac
    return {"cpi": _n(cpi), "spi": _n(ev / pv), "cv": _n(ev - ac), "sv": _n(ev - pv), "eac": _n(bac / cpi),
            "etc": _n(bac / cpi - ac), "tcpi": _n((bac - ev) / (bac - ac))}


_UNITS = {  # dimension -> {unit: factor to the dimension's base unit}
    "length": {"mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0, "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344},
    "area": {"mm2": 1e-6, "cm2": 1e-4, "m2": 1.0, "ha": 10000.0, "km2": 1e6, "in2": 0.00064516,
             "ft2": 0.09290304, "yd2": 0.83612736, "acre": 4046.8564224},
    "volume": {"ml": 1e-6, "l": 0.001, "m3": 1.0, "mm3": 1e-9, "cm3": 1e-6, "in3": 1.6387064e-05,
               "ft3": 0.028316846592, "yd3": 0.764554857984, "gal_us": 0.003785411784, "gal_uk": 0.00454609},
    "mass": {"g": 0.001, "kg": 1.0, "t": 1000.0, "lb": 0.45359237, "oz": 0.028349523125,
             "ton_us": 907.18474, "ton_uk": 1016.0469088},
    "force": {"n": 1.0, "kn": 1000.0, "mn": 1e6, "kgf": 9.80665, "lbf": 4.4482216152605, "kip": 4448.2216152605},
    "stress": {"pa": 1.0, "kpa": 1000.0, "mpa": 1e6, "gpa": 1e9, "psi": 6894.757293168,
               "ksi": 6894757.293168, "psf": 47.88025898033584, "ksf": 47880.25898033584},
    "flow": {"m3s": 1.0, "l_s": 0.001, "m3h": 1 / 3600.0, "cfs": 0.028316846592, "gpm_us": 6.30901964e-05,
             "mgd": 0.0438126364},
    "velocity": {"m_s": 1.0, "km_h": 0.2777777778, "ft_s": 0.3048, "ft_min": 0.00508, "mph": 0.44704, "knot": 0.514444},
    "power": {"w": 1.0, "kw": 1000.0, "mw": 1e6, "hp": 745.6998715823, "btu_h": 0.29307107},
    "energy": {"j": 1.0, "kj": 1000.0, "mj": 1e6, "kwh": 3.6e6, "btu": 1055.05585262, "therm": 1.05505585262e8},
}

_ALIASES = {"mm": "mm", "millimetre": "mm", "millimeter": "mm", "cm": "cm", "m": "m", "metre": "m", "meter": "m",
            "km": "km", "in": "in", "inch": "in", "inches": "in", '"': "in", "ft": "ft", "foot": "ft", "feet": "ft",
            "'": "ft", "yd": "yd", "yard": "yd", "yds": "yd", "mi": "mi", "mile": "mi", "miles": "mi",
            "sf": "ft2", "sqft": "ft2", "sy": "yd2", "sqyd": "yd2", "sqm": "m2", "sqmm": "mm2", "sqin": "in2",
            "cy": "yd3", "cuyd": "yd3", "cuft": "ft3", "cuin": "in3", "gal": "gal_us", "gallon": "gal_us",
            "lbs": "lb", "pound": "lb", "pounds": "lb", "ton": "ton_us", "tons": "ton_us", "tonne": "t",
            "tonnes": "t", "mt": "t", "kip": "kip", "kips": "kip", "psi": "psi", "ksi": "ksi", "psf": "psf",
            "ksf": "ksf", "gpm": "gpm_us", "cfm": "ft3", "fps": "ft_s", "fpm": "ft_min", "mph": "mph",
            "lps": "l_s", "ls": "l_s", "hp": "hp", "btu": "btu", "kwh": "kwh", "kn": "kn", "mn": "mn",
            "n": "n", "kg": "kg", "g": "g", "t": "t", "l": "l", "litre": "l", "liter": "l",
            "m/s": "m_s", "m3/s": "m3s", "m3/h": "m3h", "l/s": "l_s", "km/h": "km_h", "ft/s": "ft_s",
            "ft/min": "ft_min", "btu/h": "btu_h", "mm2": "mm2", "cm2": "cm2", "m2": "m2", "m3": "m3",
            "mm3": "mm3", "cm3": "cm3"}


def _unit_key(u):
    """'sq ft' / 'SQFT' / 'ft²' / 'm^2' -> a canonical unit key ('ft2')."""
    s = str(u).strip().lower().replace("²", "2").replace("³", "3").replace("^", "")
    s = _re.sub(r"[\s._-]+", "", s)
    s = s.replace("square", "sq").replace("cubic", "cu")
    if s in _ALIASES:
        return _ALIASES[s]
    return s


def unit_dimension(u):
    """The dimension a unit belongs to ('yd3' -> 'volume'), or None."""
    k = _unit_key(u)
    return next((d for d, table in _UNITS.items() if k in table), None)


def convert(value, frm, to):
    """Convert a value between metric and US units: convert(12, 'in', 'mm') -> 304.8,
    convert(100, 'yd3', 'm3') -> 76.4555, convert(50, 'ksi', 'MPa') -> 344.738. Both spellings of a unit are
    accepted ('sq ft', 'ft2', 'sf'; 'CY', 'cu yd', 'yd3'). Temperature has its own helper, convert_temp()."""
    a, b = _unit_key(frm), _unit_key(to)
    if a in ("c", "f", "k", "°c", "°f", "degc", "degf", "celsius", "fahrenheit"):
        raise ValueError("temperature is not multiplicative — use convert_temp(value, %r, %r)" % (frm, to))
    da, db = unit_dimension(a), unit_dimension(b)
    if da != db or da is None:
        raise ValueError("cannot convert %s to %s" % (frm, to))
    return float(value) * _UNITS[da][a] / _UNITS[db][b]


def convert_temp(value, frm="F", to="C"):
    """Temperature between F, C and K (K = C + 273.15; F = C x 9/5 + 32)."""
    v, a, b = float(value), str(frm).strip().upper(), str(to).strip().upper()
    c = {"F": (v - 32) * 5 / 9, "C": v, "K": v - 273.15}[a]
    return {"F": c * 9 / 5 + 32, "C": c, "K": c + 273.15}[b]


HELP = """Already defined for you (call them, do not re-implement):
- cpm(activities) — critical path, finish-to-start, no lags. activities = [{'id': 'A', 'duration': 10, 'preds': 'B, D'}, ...]
  ('preds' may be a list or a string; '—' means none). Returns {'duration': n, 'critical': [ids with zero total float],
  'by_id': {id: {'es','ef','ls','lf','tf','ff'}}}.
- pdm(activities) — precedence diagram WITH FS/SS/FF relationships and lags (day numbers). Same shape as cpm, but
  'preds' carries the relationship: 'A020 FS+3, A010 SS+1'. Returns {'duration', 'critical', 'by_id': {es,ef,ls,lf,tf}}.
- working_day_date(day0, k, holidays) — the date of working day k (day 0 is the first working day on or after day0;
  Mon–Fri, holidays skipped). Use it to turn a day number into the date an activity starts or the project finishes.
- mass_haul(cut_areas, fill_areas, length, shrink, stations=None) — average-end-area volumes and the mass diagram:
  returns {'cut_bcy','fill_ccy','net_bcy','ordinates','max_ordinate','max_index','max_station'}; max_ordinate is the
  PEAK, not the final ordinate. shrink may be 0.18 or 18. station_label(1250) -> '12+50'.
- pv(amount, rate, years), pv_annuity(payment, rate, years), npv(rate, cashflows_from_year_0), irr(cashflows)
  — rate as a fraction (7% -> 0.07); payments at the end of each year.
- evm(pv, ev, ac, bac) -> {'cpi','spi','cv','sv','eac','etc','tcpi'}.
- compound_markups(base, pcts) — markups applied in sequence to the running total (pcts as 0.08 or 8), never added.
- manning_full(diameter_in, slope, n) -> full-flow pipe capacity in cfs (Q = 1.49/n × A × R^(2/3) × S^(1/2)).
- convert(value, frm, to) — metric/US unit conversion: convert(12,'in','mm'), convert(250,'yd3','m3'),
  convert(50,'ksi','MPa'), convert(2,'cfs','m3s'), convert(1200,'sq ft','m2'). Both spellings work ('CY','cu yd','yd3';
  'sf','sq ft','ft2'). unit_dimension('yd3') -> 'volume'. convert_temp(v,'F','C') for temperature.
  If a task mixes systems, convert every input to ONE system first and state which system the answer is in.
- round_half_up(x, places=0) — rounds .5 up (Python's round() rounds .5 to even).
- parse_step(text) — an IFC/STEP file -> {'#123': {'type': 'IFCWALL', 'args': [...]}}; references stay '#n' strings,
  lists are lists, $ is None, .ENUM. is 'ENUM'. Follow references through the dict.
- box_overlap(a, b) -> [ox, oy, oz] and box_gap(a, b) -> clear distance, boxes as (x0, x1, y0, y1, z0, z1)."""
