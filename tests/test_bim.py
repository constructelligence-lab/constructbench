"""BIM & digital construction: every answer is re-derived from the prompt text alone, independently of the generator —
including the IFC tasks, which are re-read here with a separate STEP parser."""
import itertools
import math
import re
import unittest

from constructbench import registry
from constructbench.generators.bim import clash_results


def fam(name, seeds=(1, 2, 3), n=12):
    return [t for s in seeds for t in registry.build(seed=s, per_family=n, families=[name])]


def table_after(prompt, header_start):
    lines = prompt.splitlines()
    start = next(k for k, line in enumerate(lines) if line.startswith(header_start))
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


class Bim(unittest.TestCase):
    def test_clash_detection_from_the_table(self):
        outcomes = set()
        for t in fam("clash_detection"):
            clearance = int(re.search(r"clearance distance under (\d+) mm", t.prompt).group(1))
            els = [dict(id=r[0], disc=r[1], box=list(map(int, r[3:9]))) for r in table_after(t.prompt, "| ID |")]
            hard, soft = {}, 0
            for a, b in itertools.combinations(els, 2):
                if a["disc"] == b["disc"]:
                    continue
                (ax0, ax1, ay0, ay1, az0, az1), (bx0, bx1, by0, by1, bz0, bz1) = a["box"], b["box"]
                o = [min(ax1, bx1) - max(ax0, bx0), min(ay1, by1) - max(ay0, by0), min(az1, bz1) - max(az0, bz0)]
                if all(v > 0 for v in o):
                    hard["/".join(sorted((a["id"], b["id"])))] = o[0] * o[1] * o[2]
                else:
                    g = [max(0, bx0 - ax1, ax0 - bx1), max(0, by0 - ay1, ay0 - by1), max(0, bz0 - az1, az0 - bz1)]
                    soft += math.sqrt(sum(x * x for x in g)) < clearance
            self.assertEqual(sorted(t.answer["hard_clash_pairs"]), sorted(hard))
            self.assertEqual(t.answer["clearance_clash_count"], soft)
            worst = max(hard, key=hard.get)
            self.assertEqual(t.answer["largest_overlap_pair"], worst)
            self.assertAlmostEqual(t.answer["largest_overlap_volume_m3"], hard[worst] / 1e9, places=6)
            outcomes.add(len(hard))
        self.assertGreater(len(outcomes), 2)                     # the number of clashes varies

    def test_touching_faces_are_a_clearance_clash_not_a_hard_one(self):
        a = {"id": "S-01", "disc": "STR", "x0": 0, "x1": 100, "y0": 0, "y1": 100, "z0": 0, "z1": 100}
        b = {"id": "M-01", "disc": "MECH", "x0": 100, "x1": 200, "y0": 0, "y1": 100, "z0": 0, "z1": 100}
        c = {"id": "S-02", "disc": "STR", "x0": 50, "x1": 150, "y0": 0, "y1": 100, "z0": 0, "z1": 100}
        hard, soft = clash_results([a, b, c], clearance=25)
        self.assertEqual(hard, {"M-01/S-02": 50 * 100 * 100})    # S-01/S-02 overlap but share a discipline
        self.assertEqual(soft, 1)                                # S-01/M-01 touch: distance 0

    def test_ifc_quantities_by_reading_the_step_file(self):
        for t in fam("ifc_quantities"):
            step = t.prompt.split("```")[1]
            ents = {int(m.group(1)): (m.group(2), m.group(3))
                    for m in re.finditer(r"#(\d+)=([A-Z0-9]+)\((.*)\);", step)}

            def refs(s):
                return [int(x) for x in re.findall(r"#(\d+)", s)]

            def name(eid):
                return re.findall(r"'([^']*)'", ents[eid][1])[1]

            storey = {}
            qty = {}
            for eid, (typ, args) in ents.items():
                if typ == "IFCRELCONTAINEDINSPATIALSTRUCTURE":
                    inner, _, last = args.rpartition(",")
                    for e in refs(inner.split("(", 1)[1]):
                        storey[e] = name(refs(last)[0])
                if typ == "IFCRELDEFINESBYPROPERTIES":
                    inner, _, last = args.rpartition(",")
                    eq = refs(last)[0]
                    qs = {}
                    for q in refs(ents[eq][1].rsplit("(", 1)[1]):
                        qn, = re.findall(r"^'([^']*)'", ents[q][1])
                        qs[qn] = float(ents[q][1].split(",")[3])
                    for e in refs(inner.split("(", 1)[1]):
                        qty[e] = qs
            walls = [e for e, (typ, _) in ents.items() if typ == "IFCWALL"]
            slabs = [e for e, (typ, _) in ents.items() if typ == "IFCSLAB"]
            doors = [e for e, (typ, _) in ents.items() if typ == "IFCDOOR"]
            self.assertAlmostEqual(t.answer["level2_wall_net_volume_m3"],
                                   sum(qty[w]["NetVolume"] for w in walls if storey[w] == "Level 2"), places=3)
            self.assertEqual(t.answer["level1_door_count"], sum(1 for d in doors if storey[d] == "Level 1"))
            self.assertAlmostEqual(t.answer["slab_net_area_m2"], sum(qty[s]["NetArea"] for s in slabs), places=2)
            self.assertEqual(t.answer["largest_wall_by_net_side_area"], name(max(walls, key=lambda w: qty[w]["NetSideArea"])))
            for w in walls:                                       # NetVolume is never the GrossVolume
                self.assertLessEqual(qty[w]["NetVolume"], qty[w]["GrossVolume"])
            self.assertTrue(any(qty[w]["NetVolume"] < qty[w]["GrossVolume"] for w in walls))

    def test_asset_register_from_the_tables(self):
        for t in fam("asset_register"):
            rows = table_after(t.prompt, "| Tag |")
            codes = {r[0]: r[1] for r in table_after(t.prompt, "| Type | Code |")}
            missing = lambda v: v in ("", "—", "TBC")
            incomplete = sorted(r[0] for r in rows if any(missing(v) for v in r[2:6]))
            invalid = sorted(r[0] for r in rows if not re.fullmatch(re.escape(codes[r[1]]) + r"-\d\d", r[0]))
            self.assertEqual(t.answer["incomplete_assets"], incomplete)
            self.assertEqual(t.answer["invalid_tags"], invalid)
            filled = sum(not missing(v) for r in rows for v in r[2:6])
            self.assertAlmostEqual(t.answer["required_fields_complete_pct"], filled / (4 * len(rows)) * 100, places=3)
            counts = {f: sum(missing(r[k]) for r in rows) for k, f in zip(range(2, 6), ["Manufacturer", "Model", "Serial", "Space"])}
            self.assertEqual(t.answer["most_missing_attribute"], sorted(f for f, v in counts.items() if v == max(counts.values()))[0])

    def test_file_naming_from_the_code_lists(self):
        for t in fam("file_naming"):
            lists = dict(re.findall(r"^- (Project|Originator|Volume/system|Level/location|Type|Role): (.+)$", t.prompt, re.M))
            allowed = [lists["Project"].split(", "), lists["Originator"].split(", "), lists["Volume/system"].split(", "),
                       lists["Level/location"].split(", "), re.findall(r"(\w+) \(", lists["Type"]),
                       re.findall(r"(\w+) \(", lists["Role"])]
            names = re.findall(r"^- (\S+)$", t.prompt.split("Uploads this week:")[1], re.M)

            def ok(n):
                p = n.split("-")
                return len(p) == 7 and all(p[k] in allowed[k] for k in range(6)) and re.fullmatch(r"\d{4}", p[6]) is not None
            good = [n for n in names if ok(n)]
            self.assertEqual(sorted(t.answer["non_compliant_names"]), sorted(n for n in names if not ok(n)))
            self.assertEqual(t.answer["compliant_count"], len(good))
            self.assertEqual(t.answer["compliant_structural_drawings"],
                             sum(1 for n in good if n.split("-")[4:6] == ["DR", "S"]))

    def test_model_5d_from_the_schedule(self):
        for t in fam("model_5d"):
            rows = table_after(t.prompt, "| Element |")
            rates = {r[0]: float(r[1].split()[0].replace("$", "").replace(",", "")) for r in table_after(t.prompt, "| Uniformat | Rate |")}
            cost = {}
            for _, code, _, phase, q, _ in rows:
                if phase == "New":
                    cost[code] = cost.get(code, 0) + int(q.replace(",", "")) * rates[code]
            self.assertAlmostEqual(t.answer["total_cost"], sum(cost.values()), places=1)
            self.assertAlmostEqual(t.answer["shell_cost"], sum(v for c, v in cost.items() if c.startswith("B")), places=1)
            self.assertEqual(t.answer["largest_cost_code"], max(cost, key=cost.get))
            self.assertEqual(t.answer["excluded_elements"], sum(1 for r in rows if r[3] != "New"))


if __name__ == "__main__":
    unittest.main()
