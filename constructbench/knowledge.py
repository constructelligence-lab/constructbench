"""Construction reference cards the ci: agent attaches to a task: textbook formulas and the slips a small model makes
with them (units, percent vs fraction, order of markups, inclusive dates).

A card is chosen by keywords in the task text, at most a few per task. Cards hold standard practice only — never a
task's numbers — and always yield to the task: when a prompt states its own rule or figure, that wins.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Card:
    name: str
    triggers: tuple[str, ...]   # regexes, matched case-insensitively against the task text
    text: str


CARDS: tuple[Card, ...] = (
    # ── project management, cost and finance ──
    Card("earned value", (r"earned value", r"\bCPI\b", r"\bSPI\b", r"\bEAC\b", r"\bTCPI\b", r"\bBAC\b"),
         "EV = % complete × BAC; PV = % planned × BAC; AC = actual cost. CPI = EV/AC, SPI = EV/PV, CV = EV − AC, "
         "SV = EV − PV, EAC = BAC/CPI (unless the task gives another), ETC = EAC − AC, TCPI = (BAC − EV)/(BAC − AC). "
         "Percent complete is a fraction in these formulas (34% -> 0.34)."),
    Card("labor productivity", (r"productivity factor", r"earned hours", r"labor[- ]hours? per", r"budget(ed)? hours"),
         "Earned hours = budget hours × % complete. Productivity factor as the task defines it (often actual ÷ earned; "
         ">1 is worse than plan). Hours × loaded rate = cost; variance sign as the task states (overrun positive)."),
    Card("retainage and pay apps", (r"retainage", r"pay(ment)? app", r"\bG70[23]\b", r"scheduled value"),
         "Retainage held = rate × (work completed + stored materials to date) unless the task excludes stored "
         "materials. Current payment due = completed & stored to date − retainage held − previous payments. "
         "G703: G = D + E + F, H = C − G, % = G ÷ C. When retainage drops (e.g. 10% -> 5% at 50%), apply the new "
         "rate to the whole completed amount as the task says."),
    Card("WIP over/under billing", (r"work[- ]in[- ]progress", r"\bWIP\b", r"over[ /-]?billing", r"under[ -]?billed",
                                    r"percentage of completion", r"cost[- ]to[- ]cost"),
         "Cost-to-cost: % complete = cost to date ÷ estimated total cost; earned revenue = % × contract value; "
         "over(under) billing = billed to date − earned revenue (positive = overbilled, negative = underbilled). "
         "The most underbilled job has the most negative value; report the amount as the task asks (sign or size)."),
    Card("markups in sequence", (r"markup", r"\bfee\b", r"overhead (of|at|on|and|rate)", r"OH&P", r"\bbond\b", r"contingency", r"bid[- ]day"),
         "Apply markups in the stated order, each on the running total the task names: total = base × (1+a) × (1+b)"
         "… only when each applies to the running total; a markup on one part (e.g. self-performed only) applies to "
         "that part. Markup on cost: price = cost × (1+m); margin on price: price = cost ÷ (1 − m). Do not add "
         "percentages together."),
    Card("cash flow", (r"cash (flow|forecast)", r"closing balance", r"opening balance"),
         "Closing = opening + cash in − cash out; next week's opening = this week's closing. A dash (—) or blank "
         "means 0. Track the minimum and the first week it occurs."),
    Card("time value of money", (r"present value", r"discount rate", r"lifecycle cost", r"life[- ]cycle", r"\bNPV\b",
                                 r"\bIRR\b", r"annuit"),
         "PV of a single amount in year t = A ÷ (1+r)^t. PV of an equal end-of-year amount for n years = "
         "P × (1 − (1+r)^−n) ÷ r (pv_annuity). Initial cost is at year 0 (not discounted). Rate as a fraction. "
         "Lower lifecycle cost = lower total PV of cost."),
    Card("real estate pro forma", (r"\bNOI\b", r"cap(italization)? rate", r"pro ?forma", r"yield on cost",
                                   r"effective gross income", r"gross potential rent"),
         "GPR = units × rent × 12. EGI = GPR − vacancy & credit loss. NOI = EGI − operating expenses (no debt service, "
         "no depreciation). Value = NOI ÷ cap rate. Yield on cost = NOI ÷ total development cost. Soft costs as a % "
         "of hard costs are added to land + hard. Answers named _pct are percents (5.5, not 0.055)."),
    Card("facilities maintenance", (r"backlog", r"condition (index|score|rating)", r"\bFCI\b", r"criticality",
                                    r"expected life", r"deferred maintenance"),
         "Facility condition index FCI = deferred maintenance cost ÷ current replacement value (lower is better). "
         "Risk/priority scores: apply the task's formula to every row, then sort by score descending with the "
         "task's tie-break (e.g. alphabetical) — sorted(rows, key=lambda r: (-score(r), r['Asset'])). "
         "Remaining life = expected life − age; at or past expected life when age ≥ life."),
    Card("bid leveling", (r"level(ed|ing)? (these |the )?.*bids?", r"exclusions?", r"leveled"),
         "Leveled bid = base bid + the estimator's value for every scope item that bid excludes (each exclusion "
         "listed in a cell separated by commas). Compare leveled totals; spread = highest − lowest leveled total."),
    Card("RFIs and dates", (r"\bRFI", r"look[- ]ahead", r"calendar days", r"\bwindow\b", r"notice", r"deadline"),
         "Parse MM/DD/YYYY with datetime.datetime.strptime(s, '%m/%d/%Y').date(), YYYY-MM-DD with "
         "datetime.date.fromisoformat(s). Days between = (d2 − d1).days; 'within N days after' = event + "
         "timedelta(days=N). Weekend roll: while d.weekday() >= 5 (Sat=5, Sun=6): d += timedelta(days=1). "
         "An activity is active in a window when start ≤ window end and finish ≥ window start (both inclusive); it "
         "starts in the window when window start ≤ start ≤ window end. '—' means no date."),
    # ── scheduling ──
    Card("critical path", (r"critical path", r"critical activit", r"zero total float", r"total float", r"free float", r"predecessor", r"early start", r"late finish"),
         "Use cpm(activities): forward pass ES = max EF of predecessors (0 if none), EF = ES + duration; backward pass "
         "LF = min LS of successors (project finish if none), LS = LF − duration; TF = LS − ES; FF = min ES of "
         "successors − EF. Critical = TF 0. For a delay, rerun cpm with the new duration and compare durations."),
    Card("schedule quality", (r"missing (predecessor|successor)", r"negative lag", r"hard constraint",
                              r"schedule quality"),
         "Check each activity: no predecessors (except the start milestone), never named as a predecessor (except the "
         "finish milestone), any relationship lag < 0, hard constraints only as the task defines them, duration over "
         "the threshold (strictly greater). Return IDs as strings exactly as listed."),
    # ── estimating and quantities ──
    Card("quantity units", (r"cubic yard", r"\bCY\b", r"square yard", r"\bSY\b", r"take[- ]?off", r"\bLF\b",
                            r"concrete", r"sheets?\b", r"drywall", r"\bboard\b"),
         "1 CY = 27 cu ft; 1 SY = 9 sq ft; 1 square (roofing) = 100 sq ft; 1 ton = 2,000 lb. Inches to feet ÷ 12 "
         "before multiplying areas or volumes. Sheet goods (drywall, plywood): sheets = net area × (1 + waste) ÷ sheet "
         "area, rounded up. Waste: quantity × (1 + waste). Buy whole units with math.ceil only "
         "where the task says to round up."),
    Card("contract delays", (r"liquidated damages", r"excusable", r"compensable", r"concurrent", r"time extension",
                              r"extended general conditions"),
         "Excusable delay extends the completion date; compensable delay also pays (e.g. extended general conditions "
         "× compensable days). Concurrent days are usually excusable but not compensable — follow the task's rules "
         "exactly. Liquidated damages = rate × days late beyond the adjusted completion date, capped where stated. "
         "Count calendar days with datetime.date arithmetic."),
    Card("roofing", (r"roof", r"pitch", r"slope factor", r"shingle", r"bundle"),
         "Roof surface = plan area × slope factor (pitch factor = √(rise² + 12²) ÷ 12). Squares = surface ÷ 100, then "
         "× (1 + waste). Bundles = squares × bundles per square, rounded up."),
    Card("earthwork", (r"\bcut\b", r"\bfill\b", r"earthwork", r"grid method", r"end area", r"swell", r"shrink"),
         "Grid method: each cell's depth = average of its 4 corner (design − existing) values; volume = cell area × "
         "|depth| ÷ 27 CY; cut where the depth is negative, fill where positive (sum separately). A grid of R rows × C "
         "columns of points has (R−1) × (C−1) cells. Average end area: V = L × (A1 + A2) ÷ 2 ÷ 27. Loose = bank × "
         "(1 + swell); compacted = bank × (1 − shrink). Net > 0 fill means import."),
    Card("paving", (r"asphalt", r"paving", r"\bpave\b", r"base course", r"surface course", r"HMA"),
         "HMA tons = area (SY) × thickness (in) × lb per SY-inch ÷ 2,000, per course; waste on the total only if the "
         "task says so. By volume: tons = area (sf) × thickness (ft) × density (lb/cf) ÷ 2,000."),
    Card("masonry", (r"brick", r"masonry", r"\bCMU\b", r"block wall"),
         "Net wall area = gross (length × height) − openings. Units = net area × units per sf (modular brick ≈ 6.75–6.9, "
         "8×16 CMU 1.125), rounded up when the task says. Crew days = units ÷ (masons × units per mason-day)."),
    # ── architecture and codes ──
    Card("occupant load and egress", (r"occupant", r"egress", r"\bexits? (required|width|access)", r"number of exits", r"required exits", r"load factor"),
         "Occupant load per space = area ÷ load factor (net or gross as given), rounded up per space when the task "
         "says, then summed. IBC exits: one exit may serve a small space (typically < 50 occupants), 50–500 -> 2, "
         "501–1,000 -> 3, > 1,000 -> 4 — the task's own table wins. Egress width = occupants × inches per occupant "
         "(typically 0.2 in for doors and other components, 0.3 in for stairs; the task's factor wins)."),
    Card("stairs", (r"\bstairs?\b", r"\briser", r"\btread"),
         "Risers = ceil(total rise ÷ max riser); riser height = rise ÷ risers; treads = risers − 1 (straight run "
         "between floors); total run = treads × tread depth. IBC commercial: riser ≤ 7 in, tread ≥ 11 in."),
    Card("zoning", (r"\bFAR\b", r"floor area ratio", r"zoning", r"setback", r"lot coverage"),
         "Gross floor area = sum of every story's floor area. Max floor area = FAR × lot area. Lot coverage = "
         "footprint ÷ lot area. Margin = allowed − proposed (negative when over)."),
    # ── design and engineering ──
    Card("beams", (r"beam", r"bending", r"section modulus", r"deflection", r"\bspan\b"),
         "Simply supported, uniform load w: M = wL²/8, V = wL/2, Δ = 5wL⁴ ÷ (384 E I). Units: for Δ use w in lb/in "
         "(lb/ft ÷ 12) and L in inches with E in psi and I in in⁴. S required = M ÷ Fb with M in lb-in (ft-kips × "
         "12,000). L/360 limit = L (in) ÷ 360; ok when Δ ≤ limit."),
    Card("electrical", (r"three[- ]phase", r"single[- ]phase", r"\bbreaker", r"power factor", r"\bkVA\b", r"ampacity"),
         "Three-phase current I = P (W) ÷ (√3 × V × PF); single-phase I = P ÷ (V × PF); kVA = kW ÷ PF. Continuous "
         "loads: breaker ≥ 125% of the current, then the next standard size at or above it."),
    Card("ducts", (r"\bduct", r"\bCFM\b", r"\bfpm\b", r"velocity"),
         "Velocity (fpm) = CFM ÷ area (sq ft); a rectangular duct in inches: area = a × b ÷ 144. Equal-area round "
         "diameter = √(4 × area ÷ π) (in inches if area in sq in). Equal-friction equivalent "
         "De = 1.30 (ab)^0.625 ÷ (a + b)^0.25 — use only if the task asks for equal friction."),
    Card("pipes and drainage", (r"manning", r"\binvert", r"storm (sewer|drain)", r"\bcfs\b", r"gravity"),
         "Slope = (upstream invert − downstream invert) ÷ length (as a fraction in Manning; ×100 for percent). "
         "US Manning: Q = 1.49 ÷ n × A × R^(2/3) × S^(1/2), A in sq ft and R in ft — convert the diameter from inches "
         "to feet first. Full circular pipe: A = πD²/4, R = D/4."),
    # ── safety ──
    Card("incident rates", (r"\bTRIR\b", r"\bDART\b", r"\bLTIR\b", r"recordable", r"incident rate"),
         "Rate = cases × 200,000 ÷ hours worked, for each case type: TRIR (all recordables), DART (days away, "
         "restricted or transferred), LTIR (days-away/lost-time cases)."),
    Card("fall protection", (r"\blanyard", r"fall (clearance|arrest|protection)", r"D-ring", r"free fall",
                             r"\bladder", r"guardrail"),
         "Required clearance = free fall + deceleration distance (≤ 3.5 ft for shock absorbers) + D-ring height + "
         "safety factor (follow the task's formula and terms). Free fall never below 0. Ladders: extend 3 ft above "
         "the landing; 4:1 rise to setback. Guardrail top rail 42 in ± 3 in, mid-rail ~21 in."),
    Card("excavation", (r"trench", r"excavat", r"soil type", r"[Tt]ype [ABC] soil", r"shoring"),
         "OSHA 1926 Subpart P: a protective system is required at 5 ft or deeper (unless stable rock). Max slopes "
         "(H:V): Type A 0.75:1, Type B 1:1, Type C 1.5:1. Top width with both walls sloped from the bottom edge = "
         "bottom width + 2 × depth × (H/V)."),
    Card("cranes and rigging", (r"\bcrane", r"rigging", r"\bsling", r"swing radius", r"load chart"),
         "Sling tension per leg = load ÷ (legs × sin(angle from horizontal)) (or ÷ (legs × cos(angle from vertical))). "
         "Use the load chart value at the radius at or beyond the actual radius (never interpolate upward). Total "
         "load includes rigging and block weight."),
    # ── quality ──
    Card("concrete acceptance", (r"f'?c\b", r"compressive strength", r"cylinder", r"strength test", r"acceptance"),
         "ACI 318: a strength test = average of the cylinders from one sample. Acceptable when every average of 3 "
         "consecutive tests ≥ f'c and no single test < f'c − 500 psi (f'c ≤ 5,000 psi) or < 0.90 f'c (above 5,000)."),
    Card("compaction", (r"compaction", r"proctor", r"dry density", r"moisture content"),
         "Relative compaction (%) = field dry density ÷ maximum dry density × 100. Dry density = wet density ÷ "
         "(1 + moisture as a fraction). Pass when ≥ the specified %."),
    # ── sustainability ──
    Card("energy", (r"\bEUI\b", r"kBtu", r"therms?", r"\bkWh\b", r"energy use"),
         "1 kWh = 3.412 kBtu; 1 therm = 100 kBtu. Site EUI = total kBtu per year ÷ gross sq ft. Cost = kWh × $/kWh "
         "+ therms × $/therm."),
    Card("solar PV", (r"\bPV\b", r"solar", r"\bmodules?\b", r"kW-?DC", r"payback"),
         "Modules = floor(usable area ÷ module area). kW-DC = modules × W ÷ 1,000. Annual kWh = kW-DC × specific "
         "yield (kWh/kW/yr). Net cost = $/W × W × (1 − incentive). Simple payback = net cost ÷ annual savings."),
    Card("embodied carbon", (r"embodied carbon", r"CO₂e|CO2e", r"emission factor"),
         "kgCO₂e = quantity × factor (matching units); tonnes = kg ÷ 1,000. Intensity = total kg ÷ floor area. A "
         "factor reduced by p% saves quantity × factor × p in that material only."),
    # ── robotics and survey ──
    Card("differential leveling", (r"backsight", r"foresight", r"\bBS\b", r"\bFS\b", r"benchmark", r"\bBM-",
                                   r"misclosure", r"level loop"),
         "Height of instrument HI = known elevation + BS; next elevation = HI − FS; carry point to point in table "
         "order. Misclosure = computed closing elevation − known elevation (or Σ BS − Σ FS for a closed loop). "
         "Allowable misclosure is often k × √(distance) — use the task's constant and units. A negative FS (rod "
         "held upside down on a ceiling) is used with its sign."),
    Card("coordinates and kinematics", (r"easting", r"northing", r"rotated", r"link \d", r"joint \d", r"robotic arm"),
         "math.sin/cos take radians: math.radians(deg). Rotation by θ: E = E0 + x cosθ − y sinθ, N = N0 + x sinθ + "
         "y cosθ. Two-link arm: x = L1 cos θ1 + L2 cos(θ1 + θ2), y = base + L1 sin θ1 + L2 sin(θ1 + θ2) (θ2 relative "
         "to link 1). Reachable when |L1 − L2| ≤ distance ≤ L1 + L2."),
    Card("drone survey", (r"\bdrone", r"(side|front|forward|end) overlap", r"field of view", r"\bGSD\b", r"flight lines?"),
         "Footprint = 2 × altitude × tan(FOV/2) (radians). Line spacing = footprint × (1 − side overlap). Follow the "
         "task's count formula exactly (often ceil(width ÷ spacing) + 1). Minutes = distance ÷ speed ÷ 60; batteries "
         "= ceil(minutes ÷ minutes per battery)."),
    Card("rebar layout", (r"rebar", r"\bbars?\b.*spacing", r"\btie (every|each)", r"\btying\b", r"intersections"),
         "Bars across a dimension = floor((dimension − 2 × cover) ÷ spacing) + 1, all in inches. Bars running the "
         "long way are counted across the short dimension, and vice versa. Intersections = long bars × short bars."),
    # ── documents ──
    Card("document extraction", (r"OCR", r"invoice", r"delivery ticket", r"lien waiver", r"extract the fields"),
         "Copy names, numbers and IDs exactly as printed (keep prefixes like T- or J-). Dates as YYYY-MM-DD. Amounts "
         "as plain numbers. Quantity and unit are separate fields. Prefer this-load/this-invoice values over "
         "cumulative ones unless asked."),
)


def _flags(trigger: str) -> int:
    # An acronym trigger (two capitals in a row: FAR, CPI, PV) matches case-sensitively, so "so far" is not zoning.
    return 0 if re.search(r"[A-Z]{2}", trigger) else re.I


def _prose(text: str) -> str:
    """The task text without markdown table body rows (headers kept): names in rows such as an activity called
    'Roofing' or a bidder 'Harbor Crane & Rigging' say nothing about which method the task needs."""
    out, in_body = [], False
    for line in text.splitlines():
        is_row = line.lstrip().startswith("|")
        if is_row and re.fullmatch(r"\s*\|?(\s*:?-{2,}:?\s*\|)+\s*", line):
            in_body = True          # the separator: rows after it are the body
        elif is_row and in_body:
            continue
        else:
            in_body = in_body and is_row
            out.append(line)
    return "\n".join(out)


def relevant(text: str, k: int = 3) -> list[Card]:
    """The k cards whose triggers match the task's prose most often (ties keep CARDS order)."""
    text, scored = _prose(text), []
    for i, c in enumerate(CARDS):
        hits = sum(len(re.findall(t, text, _flags(t))) for t in c.triggers)
        if hits:
            scored.append((-hits, i, c))
    return [c for _, _, c in sorted(scored)[:k]]


def reference(text: str, k: int = 3) -> str:
    cards = relevant(text, k)
    if not cards:
        return ""
    return ("Construction reference (standard practice — where the task states its own rule or figure, the task wins):\n"
            + "\n".join(f"- {c.name}: {c.text}" for c in cards))


UNIT_SUFFIXES = (
    (r"_(pct|percent)$|percent$", "a percent: 12.5 means 12.5%"),
    (r"_cy$", "cubic yards"), (r"_(sf|sq_ft)$", "square feet"), (r"_sy$", "square yards"),
    (r"_in$", "inches"), (r"_ft$", "feet"), (r"_m$", "metres"), (r"_in3$", "cubic inches"),
    (r"_ft_kips$", "foot-kips"), (r"_kips$", "kips"), (r"_cfs$", "cubic feet per second"),
    (r"_fpm$", "feet per minute"), (r"_kw_dc$|_kw$", "kW"), (r"_kwh$", "kWh"), (r"_amps$", "amperes"),
    (r"_tons$", "US tons of 2,000 lb"), (r"_tco2e$", "tonnes CO2e"),
    (r"_days$", "days"), (r"_hours$", "hours"), (r"_minutes$", "minutes"), (r"_years$", "years"),
)


def unit_of(key: str, kind: str = "number") -> str:
    """The unit a key's name implies ("slope_percent" -> a percent), for number fields only. Rates named with _per_
    (cost_per_sf, kbtu_per_sf) speak for themselves and get none."""
    k = key.lower()
    if kind not in ("number", "integer") or "_per_" in k:
        return ""
    return next((u for pat, u in UNIT_SUFFIXES if re.search(pat, k)), "")
