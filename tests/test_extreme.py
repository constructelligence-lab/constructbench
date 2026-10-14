"""Extreme tier: every answer re-derived from the prompt text alone, with code written separately from the generators."""
import datetime as dt
import math
import re
import unittest

from constructbench import registry
from constructbench.agent import answer_keys
from constructbench.grading import grade
from constructbench.providers import Oracle

FAMS = ["co_reconciliation", "addendum_takeoff", "ledger_xl", "cashflow_forecast"]


def fam(name, seeds=(1, 2, 3), n=6):
    return [t for s in seeds for t in registry.build(seed=s, per_family=n, families=[name])]


def rows(prompt, marker):
    out, started = [], False
    for line in prompt[prompt.index(marker):].splitlines():
        if line.startswith("|"):
            if "---" in line:
                started = True
                continue
            if started:
                out.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif started:
            break
    return out


def dollars(s):
    return float(s.replace("$", "").replace(",", ""))


class Extreme(unittest.TestCase):
    def test_oracle_keys_and_reproducible(self):
        for name in FAMS:
            for t in fam(name, seeds=(1,), n=4):
                self.assertEqual(t.difficulty, "extreme")
                self.assertTrue(grade(t, Oracle().answer(t).text).correct, t.id)
                self.assertEqual([k for k, _ in answer_keys(t.prompt)], list(t.fields), t.id)
        a = registry.build(seed=9, per_family=2, families=FAMS)
        self.assertEqual([t.to_json() for t in a], [t.to_json() for t in registry.build(seed=9, per_family=2, families=FAMS)])

    def test_co_reconciliation_from_prompt(self):
        for t in fam("co_reconciliation"):
            original = dollars(re.search(r"Original contract sum: (\$[\d,]+)", t.prompt).group(1))
            latest = {}
            for co, rev, _, status, amt in rows(t.prompt, "| CO | Rev |"):
                r = int(rev[1:])
                if co not in latest or r > latest[co][0]:
                    latest[co] = (r, status, dollars(amt))
            rates = {m.group(1): float(m.group(2)) for m in re.finditer(r"(\w+) \$(\d+\.\d\d)", t.prompt.split("Labor rates per hour:")[1].split("\n")[0])}
            od = sum(float(h) * rates[tr] + dollars(m) * 1.15 for _, tr, h, m in rows(t.prompt, "| Ticket |"))
            approved = {co: a for co, (_, s, a) in latest.items() if s == "Approved"}
            approved["OD-01"] = od
            pending = sum(a for _, s, a in latest.values() if s == "Pending")
            over, amt = [], 0.0
            for item, billed in rows(t.prompt, "| Change item |"):
                b, allowed = dollars(billed), max(0.0, approved.get(item, 0.0))
                if b > allowed + 1e-9:
                    over.append(item); amt += b - allowed
            self.assertAlmostEqual(t.answer["revised_contract_sum"], original + sum(approved.values()), places=1)
            self.assertAlmostEqual(t.answer["approved_changes_total"], sum(approved.values()), places=1)
            self.assertAlmostEqual(t.answer["pending_exposure"], pending, places=1)
            self.assertEqual(set(t.answer["overbilled_changes"]), set(over))
            self.assertAlmostEqual(t.answer["overbilled_amount"], amt, places=1)

    def test_takeoff_from_prompt(self):
        for t in fam("addendum_takeoff"):
            finish, size, doors = {}, {}, {}
            for rid, _, sz, f, d in rows(t.prompt, "| Room |"):
                L, W = [int(a) * 12 + int(b) for a, b in re.findall(r"(\d+)'-(\d+)\"", sz)]
                finish[rid], size[rid], doors[rid] = f, (L, W), int(d)
            for line in t.prompt.splitlines():
                if line.startswith("Addendum"):
                    for clause in line.split(";"):
                        m = re.search(r"rooms? ([\d, ]+?) (?:change|changes) to ([A-Z]+-\d)", clause)
                        if m:
                            for rid in re.findall(r"\d+", m.group(1)):
                                finish[rid] = m.group(2)
                        m = re.search(r"room (\d+) is not in contract", clause)
                        if m:
                            del finish[m.group(1)]
            prods = {m.group(1): (float(m.group(2)), int(m.group(3)) / 100, float(m.group(4)))
                     for m in re.finditer(r"- ([A-Z]+-\d): .*?covering ([\d.]+) sq ft, waste (\d+)%, \$([\d.]+) per", t.prompt)}
            area = {c: 0.0 for c in prods}
            base = 0.0
            for rid, f in finish.items():
                L, W = size[rid]
                area[f] += L * W / 144
                base += 2 * (L + W) / 12 - 3 * doors[rid]
            total = 0.0
            for c, (cover, waste, price) in prods.items():
                k = math.ceil(area[c] * (1 + waste) / cover) if area[c] else 0
                self.assertEqual(t.answer[f"packages_{c.replace('-', '').lower()}"], k, (t.id, c))
                total += k * price
            rolls = math.ceil(base * 1.03 / 120)
            self.assertEqual(t.answer["base_rolls"], rolls)
            self.assertAlmostEqual(t.answer["material_total_with_tax"], (total + rolls * 96) * 1.08875, places=1)

    def test_ledger_xl_from_prompt(self):
        for t in fam("ledger_xl"):
            job = re.search(r"Job cost to date for job (J-\d+)", t.prompt).group(1)
            cutoff = dt.date.fromisoformat(re.search(r"as of (\d{4}-\d\d-\d\d)", t.prompt).group(1))
            a1, a2 = re.search(r"on (\d\d-\d{3}) \(first_code_cost\) and on (\d\d-\d{3})", t.prompt).groups()
            recs = [l.split(",") for l in re.search(r"```csv\n(.*?)```", t.prompt, re.S).group(1).strip().splitlines()[1:]]
            mine = [r for r in recs if r[1] == job and dt.date.fromisoformat(r[0]) <= cutoff]
            voided = {(r[4], r[5]) for r in mine if r[7] == "VOID"}
            seen, dup, by = set(), 0, {}
            for _, _, code, frm, vendor, doc, amt, kind in mine:
                a = float(amt)
                if kind == "VOID":
                    continue
                if kind == "INV":
                    if (vendor, doc, amt) in seen:
                        dup += 1
                        continue
                    seen.add((vendor, doc, amt))
                    if (vendor, doc) in voided:
                        continue
                if kind == "RC":
                    by[frm] = by.get(frm, 0.0) - a
                by[code] = by.get(code, 0.0) + a
            budget = {r[0]: dollars(r[1]) for r in rows(t.prompt, "| Cost code |")}
            over = {c: by.get(c, 0.0) - b for c, b in budget.items()}
            self.assertAlmostEqual(t.answer["total_cost_to_date"], sum(by.values()), places=2)
            self.assertAlmostEqual(t.answer["first_code_cost"], by.get(a1, 0.0), places=2)
            self.assertAlmostEqual(t.answer["second_code_cost"], by.get(a2, 0.0), places=2)
            self.assertEqual(t.answer["duplicate_rows_removed"], dup)
            self.assertEqual(set(t.answer["codes_over_budget"]), {c for c, v in over.items() if v > 0})
            self.assertEqual(t.answer["largest_overrun_code"], max(over, key=over.get))
            self.assertTrue(any(r[7] == "RC" for r in mine))

    def test_cashflow_from_prompt(self):
        for t in fam("cashflow_forecast"):
            acts = [(int(s), int(d), dollars(c)) for _, s, d, c in rows(t.prompt, "| Activity |")]
            split = int(re.search(r"pays (\d+)% of each month", t.prompt).group(1)) / 100
            markup = int(re.search(r"plus (\d+)% markup", t.prompt).group(1)) / 100
            ret = int(re.search(r"withholds (\d+)% retainage", t.prompt).group(1)) / 100
            lag = int(re.search(r"the rest (\d+) months? after", t.prompt).group(1))
            last = max(s + d - 1 for s, d, _ in acts)
            H = last + 10
            cost = [0.0] * (H + 1)
            for s, d, c in acts:
                for m in range(s, s + d):
                    cost[m] += c / d
            flow = [0.0] * (H + 1)
            held = 0.0
            for m in range(1, last + 1):
                flow[m] -= cost[m] * split
                flow[m + 1] -= cost[m] * (1 - split)
                flow[m + lag] += cost[m] * (1 + markup) * (1 - ret)
                held += cost[m] * (1 + markup) * ret
            flow[last + 3] += held
            pos, cum = [], 0.0
            for m in range(1, last + lag + 4):
                cum += flow[m]
                pos.append(cum)
            k = min(range(len(pos)), key=pos.__getitem__)
            back = next(j + 1 for j in range(k, len(pos)) if pos[j] >= 0)
            self.assertAlmostEqual(t.answer["peak_deficit"], pos[k], places=1)
            self.assertEqual(t.answer["peak_deficit_month"], k + 1)
            self.assertEqual(t.answer["first_month_back_to_positive"], back)
            self.assertAlmostEqual(t.answer["final_cash_position"], pos[-1], places=1)


if __name__ == "__main__":
    unittest.main()
