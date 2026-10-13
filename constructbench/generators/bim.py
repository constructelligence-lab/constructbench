"""BIM & digital construction: the checks a BIM coordinator, a VDC engineer and a model-based estimator do.

Clash detection on element bounding boxes, quantities read out of an IFC (STEP) file, handover data QA on a
COBie-style asset register, ISO 19650 file naming, and a 5D cost roll-up from a model schedule. Every rule is
stated in the prompt, so each task has one right answer and the score is the reading and the arithmetic.
"""
from __future__ import annotations

import itertools
import math
import random
import string

from ..task import Task, number, INTEGER, TEXT, SET, answer_keys_line
from .common import JOB_NAMES, job_no, money, pick


# ── Clash detection ──────────────────────────────────────────────────────────────────────────────────────

DISCIPLINES = {"STR": "Structural", "MECH": "Mechanical", "PLMB": "Plumbing", "ELEC": "Electrical"}


def _overlap(a: dict, b: dict) -> list[int]:
    return [min(a[f"{x}1"], b[f"{x}1"]) - max(a[f"{x}0"], b[f"{x}0"]) for x in "xyz"]


def _gap(a: dict, b: dict) -> float:
    g = [max(0, b[f"{x}0"] - a[f"{x}1"], a[f"{x}0"] - b[f"{x}1"]) for x in "xyz"]
    return math.sqrt(sum(v * v for v in g))


def clash_results(elements: list[dict], clearance: int) -> tuple[dict, int]:
    """Hard clashes {pair: overlap mm³} and the number of clearance clashes, between different disciplines."""
    hard, soft = {}, 0
    for a, b in itertools.combinations(elements, 2):
        if a["disc"] == b["disc"]:
            continue
        o = _overlap(a, b)
        pair = "/".join(sorted((a["id"], b["id"])))
        if all(v > 0 for v in o):
            hard[pair] = o[0] * o[1] * o[2]
        elif _gap(a, b) < clearance:
            soft += 1
    return hard, soft


def _box(rng: random.Random, kind: str, n: int) -> dict:
    if kind == "beam":            # runs along x
        y = rng.randrange(500, 9000, 50); z = rng.randrange(3000, 3300, 25); d = pick(rng, [450, 530, 610])
        return {"id": f"S-{n:02d}", "disc": "STR", "what": f"Steel beam W{pick(rng, [18, 21, 24])}", "x0": 0, "x1": 12000,
                "y0": y, "y1": y + pick(rng, [190, 210, 230]), "z0": z, "z1": z + d}
    if kind == "column":
        x = rng.randrange(400, 11200, 100); y = rng.randrange(400, 9200, 100); s = pick(rng, [350, 400, 450])
        return {"id": f"S-{n:02d}", "disc": "STR", "what": "Concrete column", "x0": x, "x1": x + s, "y0": y, "y1": y + s,
                "z0": 0, "z1": 4200}
    if kind == "duct":            # runs along y
        x = rng.randrange(300, 11000, 50); w = pick(rng, [600, 800, 1000, 1200]); h = pick(rng, [300, 400, 500])
        z = rng.randrange(2500, 3600, 25)
        return {"id": f"M-{n:02d}", "disc": "MECH", "what": f"Supply duct {w}×{h}", "x0": x, "x1": x + w, "y0": 0,
                "y1": 10000, "z0": z, "z1": z + h}
    if kind == "pipe":            # runs along x, boxed by its outside diameter
        y = rng.randrange(300, 9500, 25); d = pick(rng, [110, 160, 220]); z = rng.randrange(2600, 3700, 25)
        return {"id": f"P-{n:02d}", "disc": "PLMB", "what": f"Drain pipe Ø{d}", "x0": 0, "x1": 12000, "y0": y, "y1": y + d,
                "z0": z, "z1": z + d}
    y = rng.randrange(300, 9500, 25); z = rng.randrange(2700, 3700, 25)   # cable tray along x
    return {"id": f"E-{n:02d}", "disc": "ELEC", "what": "Cable tray 300×100", "x0": 0, "x1": 12000, "y0": y, "y1": y + 300,
            "z0": z, "z1": z + 100}


def clash_detection(rng: random.Random, i: int) -> Task:
    """Axis-aligned bounding boxes: hard clashes (positive overlap on all three axes) and clearance clashes."""
    clearance = pick(rng, [25, 50, 75, 100])
    while True:
        kinds = ["beam"] * rng.randint(2, 3) + ["column"] * rng.randint(1, 2) + ["duct"] * rng.randint(2, 3) + \
                ["pipe"] * rng.randint(1, 3) + ["tray"] * rng.randint(1, 2)
        counter: dict[str, int] = {}
        elements = []
        for k in kinds:
            d = {"beam": "S", "column": "S", "duct": "M", "pipe": "P", "tray": "E"}[k]
            counter[d] = counter.get(d, 0) + 1
            elements.append(_box(rng, k, counter[d]))
        hard, soft = clash_results(elements, clearance)
        vols = sorted(hard.values(), reverse=True)
        if 1 <= len(hard) <= 6 and soft >= 1 and (len(vols) == 1 or vols[0] != vols[1]):
            break
    worst = max(hard, key=hard.get)
    rows = "\n".join(f"| {e['id']} | {e['disc']} | {e['what']} | {e['x0']} | {e['x1']} | {e['y0']} | {e['y1']} | "
                     f"{e['z0']} | {e['z1']} |" for e in elements)
    fields = {"hard_clash_pairs": SET, "clearance_clash_count": INTEGER, "largest_overlap_pair": TEXT,
              "largest_overlap_volume_m3": number(rel_tol=0.001, abs_tol=0.00005)}
    prompt = (f"Coordinate the ceiling zone of one structural bay on {pick(rng, JOB_NAMES)} ({job_no(rng)}). The federated model's "
              "elements are exported as axis-aligned bounding boxes in millimetres (project coordinates):\n\n"
              "| ID | Discipline | Element | X min | X max | Y min | Y max | Z min | Z max |\n|---|---|---|---|---|---|---|---|---|\n"
              f"{rows}\n\nClash rules: only pairs from different disciplines are tested. A hard clash is a pair whose boxes overlap "
              "by more than 0 mm on all three axes (touching faces are not a hard clash). For every other pair, the clearance "
              "distance is √(gx² + gy² + gz²), where on each axis the gap is max(0, B min − A max, A min − B max); a pair with no "
              f"hard clash and a clearance distance under {clearance} mm is a clearance clash. Give the hard-clash pairs (each "
              "written as the two IDs in alphabetical order joined by \"/\", e.g. \"M-01/S-02\"), the number of clearance clashes, "
              "the hard-clash pair with the largest overlap volume, and that volume in cubic metres.\n" + answer_keys_line(fields))
    return Task(f"bim-clash-{i:04d}", "bim", "clash_detection", "Clash detection on bounding boxes", "hard", prompt,
                {"hard_clash_pairs": sorted(hard), "clearance_clash_count": soft, "largest_overlap_pair": worst,
                 "largest_overlap_volume_m3": round(hard[worst] / 1e9, 6)}, fields)


# ── IFC quantity extraction ──────────────────────────────────────────────────────────────────────────────

_GUID_CHARS = string.digits + string.ascii_uppercase + string.ascii_lowercase + "_$"


def _guid(rng: random.Random) -> str:
    return pick(rng, list("0123")) + "".join(rng.choice(_GUID_CHARS) for _ in range(21))


def ifc_quantities(rng: random.Random, i: int) -> Task:
    """Walk an IFC4 STEP excerpt: spatial containment, element quantities, and which quantity name to use."""
    lines: list[str] = []
    nid = [100]

    def ent(text: str) -> int:
        nid[0] += rng.randint(1, 3)
        lines.append(f"#{nid[0]}={text};")
        return nid[0]

    storeys = {}
    for name, elev in (("Level 1", 0.0), ("Level 2", pick(rng, [3.6, 4.0, 4.2, 4.5]))):
        storeys[name] = ent(f"IFCBUILDINGSTOREY('{_guid(rng)}',#5,'{name}',$,$,#20,$,$,.ELEMENT.,{elev})")
    contained: dict[str, list[int]] = {n: [] for n in storeys}
    rels: list[str] = []
    walls, slabs, doors = [], [], []
    wall_types = {"Basic Wall:Exterior - 300 Brick/Block": 0.3, "Basic Wall:Interior - 138 Partition": 0.138,
                  "Basic Wall:Core - 250 Concrete": 0.25, "Basic Wall:Interior - 200 Blockwork": 0.2}
    for k in range(rng.randint(5, 8)):
        lvl = pick(rng, list(storeys))
        name = f"W-{k + 1:03d}"          # neutral: the storey must come from the containment relationship
        wtype = pick(rng, sorted(wall_types))
        length, height, thick = rng.uniform(3, 14), rng.uniform(2.8, 4.0), wall_types[wtype]
        openings = rng.uniform(0, 0.15) * length * height
        side = round(length * height - openings, 3)
        net_v, gross_v = round(side * thick, 3), round(length * height * thick, 3)
        w = ent(f"IFCWALL('{_guid(rng)}',#5,'{name}',$,'{wtype}',#30,#31,'{rng.randint(100000, 999999)}',.STANDARD.)")
        q = [ent(f"IFCQUANTITYLENGTH('Length',$,$,{round(length, 3)},$)"), ent(f"IFCQUANTITYAREA('NetSideArea',$,$,{side},$)"),
             ent(f"IFCQUANTITYVOLUME('GrossVolume',$,$,{gross_v},$)"), ent(f"IFCQUANTITYVOLUME('NetVolume',$,$,{net_v},$)")]
        rng.shuffle(q)
        eq = ent(f"IFCELEMENTQUANTITY('{_guid(rng)}',#5,'Qto_WallBaseQuantities',$,$,({','.join(f'#{x}' for x in q)}))")
        rels.append(f"IFCRELDEFINESBYPROPERTIES('{_guid(rng)}',#5,$,$,(#{w}),#{eq})")
        contained[lvl].append(w)
        walls.append({"name": name, "level": lvl, "net_v": net_v, "side": side})
    for k in range(rng.randint(2, 3)):
        lvl = pick(rng, list(storeys))
        area = round(rng.uniform(40, 260), 2)
        depth = pick(rng, [0.15, 0.2, 0.25])
        s = ent(f"IFCSLAB('{_guid(rng)}',#5,'SL-{k + 1:02d}',$,'Floor:Concrete {int(depth * 1000)}',#30,#31,'{rng.randint(100000, 999999)}',.FLOOR.)")
        q = [ent(f"IFCQUANTITYAREA('GrossArea',$,$,{round(area * rng.uniform(1.02, 1.08), 2)},$)"),
             ent(f"IFCQUANTITYAREA('NetArea',$,$,{area},$)"), ent(f"IFCQUANTITYVOLUME('NetVolume',$,$,{round(area * depth, 3)},$)")]
        rng.shuffle(q)
        eq = ent(f"IFCELEMENTQUANTITY('{_guid(rng)}',#5,'Qto_SlabBaseQuantities',$,$,({','.join(f'#{x}' for x in q)}))")
        rels.append(f"IFCRELDEFINESBYPROPERTIES('{_guid(rng)}',#5,$,$,(#{s}),#{eq})")
        contained[lvl].append(s)
        slabs.append(area)
    for k in range(rng.randint(3, 7)):
        lvl = pick(rng, list(storeys))
        d = ent(f"IFCDOOR('{_guid(rng)}',#5,'D-{k + 1:02d}',$,'Single-Flush:{pick(rng, ['915', '1015'])} x 2134mm',#30,#31,"
                f"'{rng.randint(100000, 999999)}',2.134,{pick(rng, [0.915, 1.015])},.DOOR.,.SINGLE_SWING_LEFT.,$)")
        contained[lvl].append(d)
        doors.append(lvl)
    for lvl, ids in contained.items():
        rels.append(f"IFCRELCONTAINEDINSPATIALSTRUCTURE('{_guid(rng)}',#5,$,$,({','.join(f'#{x}' for x in ids)}),#{storeys[lvl]})")
    rng.shuffle(rels)
    for r in rels:
        ent(r)
    step = "\n".join(lines)
    l2_walls = [w for w in walls if w["level"] == "Level 2"]
    if not l2_walls or "Level 1" not in doors or len({w["side"] for w in walls}) != len(walls):
        return ifc_quantities(rng, i)          # resample: the questions need a Level 2 wall and a Level 1 door
    biggest = max(walls, key=lambda w: w["side"])
    fields = {"level2_wall_net_volume_m3": number(rel_tol=0.0005, abs_tol=0.0005), "level1_door_count": INTEGER,
              "slab_net_area_m2": number(rel_tol=0.0005, abs_tol=0.005), "largest_wall_by_net_side_area": TEXT}
    prompt = ("Below is an excerpt of an IFC4 model file (STEP physical file syntax; lengths in metres, areas in m², volumes in m³; "
              "#5 is the owner history and #20/#30/#31 are placements and representations not shown). Elements are assigned to "
              "storeys by IFCRELCONTAINEDINSPATIALSTRUCTURE (its 5th attribute lists the elements, its 6th is the storey), and "
              "quantity sets are attached by IFCRELDEFINESBYPROPERTIES (5th attribute: the elements; 6th: the IFCELEMENTQUANTITY). "
              "An element's Name is its 3rd attribute.\n\n```\n" + step + "\n```\n\nGive the total NetVolume of the walls on "
              "Level 2, the number of doors on Level 1, the total NetArea of all slabs, and the Name of the wall with the largest "
              "NetSideArea.\n" + answer_keys_line(fields))
    return Task(f"bim-ifc-{i:04d}", "bim", "ifc_quantities", "Quantities from an IFC file", "hard", prompt,
                {"level2_wall_net_volume_m3": round(sum(w["net_v"] for w in l2_walls), 4),
                 "level1_door_count": doors.count("Level 1"), "slab_net_area_m2": round(sum(slabs), 3),
                 "largest_wall_by_net_side_area": biggest["name"]}, fields)


# ── Handover data QA (COBie-style asset register) ────────────────────────────────────────────────────────

ASSET_TYPES = {"AHU": "Air handling unit", "FCU": "Fan coil unit", "PMP": "Pump", "BLR": "Boiler", "EF": "Exhaust fan",
               "VAV": "VAV box", "CH": "Chiller"}
MAKERS = ["Northwind Air", "Calder HVAC", "Torrent Pumps", "Ember Boilers", "Polar Systems"]
REQUIRED = ["Manufacturer", "Model", "Serial", "Space"]


def asset_register(rng: random.Random, i: int) -> Task:
    """Required attributes present, and tags that follow the PREFIX-NN rule for their type."""
    while True:
        codes = rng.sample(sorted(ASSET_TYPES), rng.randint(3, 5))
        rows, seen = [], set()
        for k in range(rng.randint(8, 12)):
            code = pick(rng, codes)
            n = rng.randint(1, 12)
            tag = f"{code}-{n:02d}"
            fault = rng.random()
            if fault < 0.12:
                tag = f"{pick(rng, [c for c in ASSET_TYPES if c != code])}-{n:02d}"     # prefix of another type
            elif fault < 0.2:
                tag = f"{code}-{n}" if n < 10 else f"{code}{n:02d}"                       # one digit / no hyphen
            if tag in seen:
                continue
            seen.add(tag)
            vals = {"Manufacturer": pick(rng, MAKERS), "Model": f"{code[:2]}-{rng.randint(100, 990)}",
                    "Serial": f"SN{rng.randint(10000, 99999)}", "Space": f"{rng.randint(0, 4)}{rng.randint(1, 30):02d}"}
            for f in REQUIRED:
                if rng.random() < 0.13:
                    vals[f] = pick(rng, ["", "—", "TBC"])
            rows.append({"tag": tag, "type": ASSET_TYPES[code], "code": code, **vals})
        missing = {f: sum(1 for r in rows if r[f] in ("", "—", "TBC")) for f in REQUIRED}
        top = max(missing.values())
        incomplete = sorted(r["tag"] for r in rows if any(r[f] in ("", "—", "TBC") for f in REQUIRED))
        invalid = sorted(r["tag"] for r in rows if not _tag_ok(r["tag"], r["code"]))
        if incomplete and invalid and top > 0:
            break
    most = sorted(f for f, v in missing.items() if v == top)[0]
    filled = sum(len(REQUIRED) - sum(1 for f in REQUIRED if r[f] in ("", "—", "TBC")) for r in rows)
    type_table = "\n".join(f"| {ASSET_TYPES[c]} | {c} |" for c in sorted(codes))
    table = "\n".join(f"| {r['tag']} | {r['type']} | {r['Manufacturer']} | {r['Model']} | {r['Serial']} | {r['Space']} |"
                      for r in rows)
    fields = {"incomplete_assets": SET, "invalid_tags": SET, "required_fields_complete_pct": number(abs_tol=0.05),
              "most_missing_attribute": TEXT}
    prompt = ("Check this asset register (exported from the model's Component data for handover, COBie-style) before it goes "
              f"to the owner's facilities team on {job_no(rng)}.\n\n| Tag | Type | Manufacturer | Model | Serial | Space |\n"
              f"|---|---|---|---|---|---|\n{table}\n\nType codes:\n\n| Type | Code |\n|---|---|\n{type_table}\n\nRules: Manufacturer, "
              "Model, Serial and Space are required; a blank cell, \"—\" or \"TBC\" counts as missing. A tag is valid only when it is "
              "the code for its type, a hyphen, and exactly two digits (e.g. AHU-03). Give the tags of assets missing at least one "
              "required attribute, the invalid tags, the percent of required cells that are filled (over all assets), and the "
              "required attribute missing most often (ties: the alphabetically first).\n" + answer_keys_line(fields))
    return Task(f"bim-cobie-{i:04d}", "bim", "asset_register", "Handover asset data QA", "medium", prompt,
                {"incomplete_assets": incomplete, "invalid_tags": invalid,
                 "required_fields_complete_pct": round(filled / (len(rows) * len(REQUIRED)) * 100, 4),
                 "most_missing_attribute": most}, fields)


def _tag_ok(tag: str, code: str) -> bool:
    prefix, _, digits = tag.partition("-")
    return prefix == code and len(digits) == 2 and digits.isdigit()


# ── ISO 19650 information container naming ──────────────────────────────────────────────────────────────

ORIGINATORS = ["ACM", "BLD", "KRE", "NSE", "TFA"]
VOLUMES = ["ZZ", "XX", "B1", "B2"]
LEVELS = ["00", "01", "02", "03", "04", "B1", "RF", "ZZ", "XX"]
TYPES = {"DR": "drawing", "M3": "3D model", "SP": "specification", "RP": "report", "SH": "schedule"}
ROLES = {"A": "architect", "S": "structural engineer", "M": "mechanical engineer", "E": "electrical engineer",
         "C": "civil engineer"}


def naming_ok(name: str, project: str, originators: list[str]) -> bool:
    parts = name.split("-")
    return (len(parts) == 7 and parts[0] == project and parts[1] in originators and parts[2] in VOLUMES
            and parts[3] in LEVELS and parts[4] in TYPES and parts[5] in ROLES
            and len(parts[6]) == 4 and parts[6].isdigit())


def file_naming(rng: random.Random, i: int) -> Task:
    """Information container IDs: Project-Originator-Volume-Level-Type-Role-Number against the project's code lists."""
    project = "".join(rng.choice(string.ascii_uppercase) for _ in range(3))
    originators = rng.sample(ORIGINATORS, 3)
    while True:
        names = []
        for _ in range(rng.randint(10, 14)):
            p = [project, pick(rng, originators), pick(rng, VOLUMES), pick(rng, LEVELS), pick(rng, list(TYPES)),
                 pick(rng, list(ROLES)), f"{rng.randint(1, 9999):04d}"]
            fault = rng.random()
            if fault < 0.07:
                p[1] = pick(rng, [o for o in ORIGINATORS if o not in originators])            # unregistered originator
            elif fault < 0.13:
                p[6] = p[6][1:]                                                              # three-digit number
            elif fault < 0.19:
                p[4] = pick(rng, ["DWG", "MD", "dr"])                                        # not a type code
            elif fault < 0.24:
                p[3] = pick(rng, ["L2", "2", "Lvl02"])
            elif fault < 0.28:
                p[0] = project[::-1] if project[::-1] != project else "XQZ"                  # wrong project
            name = "-".join(p)
            if fault >= 0.28 and fault < 0.32:
                name = "_".join(p)                                                           # wrong delimiter
            if name not in names:
                names.append(name)
        good = [n for n in names if naming_ok(n, project, originators)]
        if 2 <= len(names) - len(good) <= 6:
            break
    s_drawings = sum(1 for n in good if n.split("-")[4] == "DR" and n.split("-")[5] == "S")
    fields = {"non_compliant_names": SET, "compliant_count": INTEGER, "compliant_structural_drawings": INTEGER}
    listing = "\n".join(f"- {n}" for n in names)
    prompt = (f"The common data environment for project {project} ({pick(rng, JOB_NAMES)}) names every information container "
              "Project-Originator-Volume-Level-Type-Role-Number (ISO 19650-2 style), seven fields joined by hyphens. This "
              f"project's code lists:\n- Project: {project}\n- Originator: {', '.join(originators)}\n- Volume/system: "
              f"{', '.join(VOLUMES)}\n- Level/location: {', '.join(LEVELS)}\n- Type: "
              + ", ".join(f"{k} ({v})" for k, v in TYPES.items()) + "\n- Role: "
              + ", ".join(f"{k} ({v})" for k, v in ROLES.items()) + "\n- Number: exactly four digits\n"
              "Codes are case-sensitive. Uploads this week:\n\n" + listing + "\n\nGive the names that do not comply, the number "
              "that do, and how many compliant names are structural engineer drawings (Type DR, Role S).\n"
              + answer_keys_line(fields))
    return Task(f"bim-name-{i:04d}", "bim", "file_naming", "ISO 19650 container naming", "medium", prompt,
                {"non_compliant_names": [n for n in names if n not in good], "compliant_count": len(good),
                 "compliant_structural_drawings": s_drawings}, fields)


# ── 5D: cost from a model element schedule ───────────────────────────────────────────────────────────────

UNIFORMAT = {"A1010": ("Standard foundations", "CY", 520, 1400), "A1030": ("Slab on grade", "SF", 9, 16),
             "B1010": ("Floor construction", "SF", 24, 41), "B2010": ("Exterior walls", "SF", 48, 95),
             "B2020": ("Exterior windows", "SF", 70, 140), "B3010": ("Roof coverings", "SF", 14, 30),
             "C1010": ("Partitions", "SF", 11, 24), "C3020": ("Floor finishes", "SF", 6, 19),
             "D3040": ("HVAC distribution", "LF", 45, 120), "D5020": ("Lighting & branch wiring", "SF", 7, 15)}
GROUPS = {"A": "Substructure", "B": "Shell", "C": "Interiors", "D": "Services"}


def model_5d(rng: random.Random, i: int) -> Task:
    """Element quantities × unit rates by Uniformat code, new construction only, rolled up to Uniformat groups."""
    while True:
        codes = rng.sample(sorted(UNIFORMAT), rng.randint(6, 8))
        rates = {c: round(rng.uniform(UNIFORMAT[c][2], UNIFORMAT[c][3]), 2) for c in codes}
        rows = []
        for k in range(rng.randint(9, 13)):
            c = pick(rng, codes)
            unit = UNIFORMAT[c][1]
            q = rng.randint(20, 400) if unit == "CY" else rng.randint(150, 9000)
            phase = "New" if rng.random() < 0.78 else pick(rng, ["Existing", "Demolished"])
            rows.append({"id": f"EL-{1000 + rng.randint(0, 899) + k * 1000}", "code": c, "phase": phase, "q": q})
        costs: dict[str, float] = {}
        for r in rows:
            if r["phase"] == "New":
                costs[r["code"]] = costs.get(r["code"], 0) + r["q"] * rates[r["code"]]
        ranked = sorted(costs.values(), reverse=True)
        if len(ranked) >= 2 and ranked[0] != ranked[1] and any(r["phase"] != "New" for r in rows) \
                and any(c.startswith("B") for c in costs):
            break
    total = sum(costs.values())
    shell = sum(v for c, v in costs.items() if c.startswith("B"))
    top = max(costs, key=costs.get)
    table = "\n".join(f"| {r['id']} | {r['code']} | {UNIFORMAT[r['code']][0]} | {r['phase']} | {r['q']:,} | {UNIFORMAT[r['code']][1]} |"
                      for r in rows)
    rate_table = "\n".join(f"| {c} | {money(rates[c], cents=True)} per {UNIFORMAT[c][1]} |" for c in sorted(codes))
    fields = {"total_cost": number(abs_tol=0.5), "shell_cost": number(abs_tol=0.5), "largest_cost_code": TEXT,
              "excluded_elements": INTEGER}
    prompt = (f"Price this model element schedule for {pick(rng, JOB_NAMES)} ({job_no(rng)}), a renovation and addition. "
              "Quantities are the model's, by Uniformat II element code:\n\n"
              "| Element | Uniformat | Description | Phase | Quantity | Unit |\n|---|---|---|---|---|---|\n" + table +
              "\n\nUnit rates:\n\n| Uniformat | Rate |\n|---|---|\n" + rate_table +
              "\n\nOnly elements in the New phase are priced (Existing and Demolished elements are excluded). Cost = quantity × "
              "rate. The first letter of a code is its group: " + ", ".join(f"{k} {v}" for k, v in GROUPS.items()) +
              ". Give the total cost, the Shell (B) cost, the Uniformat code with the largest cost, and how many elements are "
              "excluded.\n" + answer_keys_line(fields))
    return Task(f"bim-5d-{i:04d}", "bim", "model_5d", "5D cost from a model schedule", "medium", prompt,
                {"total_cost": round(total, 2), "shell_cost": round(shell, 2), "largest_cost_code": top,
                 "excluded_elements": sum(1 for r in rows if r["phase"] != "New")}, fields)
