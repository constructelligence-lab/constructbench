"""Hidden-rule and chained families, re-derived from the prompt text alone.

For the hidden-rule families the test must read the governing terms out of the contract excerpt (it never sees the
generator's rule variant), which also proves that every rule deciding the answer is actually in the excerpt.
"""
import datetime as dt
import math
import re
import unittest

from constructbench import registry
from constructbench.agent import answer_keys
from constructbench.generators.contractual import chain_values
from constructbench.grading import grade
from constructbench.providers import Oracle

FAMS = ["pay_app_contract", "delay_contract", "chained_concrete"]


def fam(name, seeds=(1, 2, 3), n=10):
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


def clause(prompt, sec):
    return next(l for l in prompt.splitlines() if l.startswith(sec + " "))


class Contractual(unittest.TestCase):
    def test_oracle_keys_and_reproducible(self):
        for name in FAMS:
            for t in fam(name, seeds=(1,), n=4):
                self.assertEqual(t.difficulty, "extreme")
                self.assertTrue(grade(t, Oracle().answer(t).text).correct, t.id)
                self.assertEqual([k for k, _ in answer_keys(t.prompt)], list(t.fields), t.id)
        a = registry.build(seed=9, per_family=2, families=FAMS)
        self.assertEqual([t.to_json() for t in a], [t.to_json() for t in registry.build(seed=9, per_family=2, families=FAMS)])

    def test_pay_app_from_contract_text(self):
        schemes = set()
        for t in fam("pay_app_contract"):
            ret_c, stored_c = clause(t.prompt, "§9.4"), clause(t.prompt, "§9.5")
            only_approved_offsite = "only if stored in a bonded warehouse" in stored_c
            prev = dollars(re.search(r"Previous certificates for payment total (\$[\d,]+)", t.prompt).group(1))
            errs, excl, C, DE, F = [], [], 0.0, 0.0, 0.0
            for it, desc, c, d, e, f, loc, g, h in rows(t.prompt, "| Item |"):
                c, d, e, f, g, h = map(dollars, (c, d, e, f, g, h))
                if "unsigned" in desc or "proposed" in desc:
                    excl.append(it)
                    continue
                if g != d + e + f or h != c - (d + e + f):
                    errs.append(it)
                C += c; DE += d + e
                F += 0 if (only_approved_offsite and "not approved" in loc) else f
            if "five percent (5%) of each payment" in ret_c:
                ret = 0.05 * (DE + F); schemes.add("flat")
            elif "No retainage is held on payable stored materials" in ret_c:
                ret = 0.10 * DE; schemes.add("no-stored")
            else:
                ret = (0.05 if (DE + F) / C > 0.5 else 0.10) * DE + 0.10 * F; schemes.add("step")
            self.assertEqual(set(t.answer["error_lines"]), set(errs), t.id)
            self.assertEqual(set(t.answer["excluded_lines"]), set(excl), t.id)
            self.assertAlmostEqual(t.answer["payable_completed_and_stored"], DE + F, places=2)
            self.assertAlmostEqual(t.answer["retainage"], ret, places=2)
            self.assertAlmostEqual(t.answer["amount_due"], DE + F - ret - prev, places=2)
            self.assertGreaterEqual(sum(1 for l in t.prompt.splitlines() if l.startswith("§")), 10)   # distractors present
        self.assertEqual(schemes, {"flat", "no-stored", "step"})

    def test_delay_from_contract_text(self):
        variants = set()
        for t in fam("delay_contract"):
            csum = dollars(re.search(r"Contract Sum is (\$[\d,]+)", t.prompt).group(1))
            original = dt.date.fromisoformat(re.search(r"achieved by (\d{4}-\d\d-\d\d)", t.prompt).group(1))
            notice = int(re.search(r"within (\d+) calendar days after the delay begins", t.prompt).group(1))
            excusable_conc = "excusable but not compensable" in clause(t.prompt, "§8.5")
            gc = dollars(re.search(r"general conditions of (\$[\d,]+) per day", t.prompt).group(1))
            ld_rate, cap = re.search(r"pays (\$[\d,]+) per day, limited in total to ([\d.]+)% of", t.prompt).groups()
            actual = dt.date.fromisoformat(re.search(r"Actual Substantial Completion was (\d{4}-\d\d-\d\d)", t.prompt).group(1))
            ant = {m: int(n) for m, n in re.findall(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d+)",
                                                   t.prompt.split("Exhibit W —")[1].split("\n")[0])}
            days = {}
            for _, who, s, e, crit, nt in rows(t.prompt, "| Delay |"):
                s, e, nt = dt.date.fromisoformat(s), dt.date.fromisoformat(e), dt.date.fromisoformat(nt)
                if crit != "Yes" or (who == "Owner" and (nt - s).days > notice):
                    continue
                d = s
                while d <= e:
                    days.setdefault(d, set()).add(who); d += dt.timedelta(days=1)
            owner = sum(1 for w in days.values() if w == {"Owner"})
            conc = sum(1 for w in days.values() if len(w) == 2)
            weather = sum(max(0, int(n) - ant[m.split()[0]]) for m, n in rows(t.prompt, "| Month |"))
            ext = owner + (conc if excusable_conc else 0) + weather
            ld_days = max(0, (actual - (original + dt.timedelta(days=ext))).days)
            self.assertEqual(t.answer["extension_days"], ext, t.id)
            self.assertEqual(t.answer["extended_completion_date"], (original + dt.timedelta(days=ext)).isoformat())
            self.assertAlmostEqual(t.answer["compensable_amount"], owner * gc)
            self.assertAlmostEqual(t.answer["liquidated_damages"],
                                   min(ld_days * dollars(ld_rate), float(cap) / 100 * csum), places=2)
            variants.add((excusable_conc, ld_days * dollars(ld_rate) > float(cap) / 100 * csum))
        self.assertEqual(len(variants), 4)          # both concurrency rules occur, with and without the LD cap binding

    def test_chained_from_prompt(self):
        num = lambda pat, t: float(re.search(pat, t.prompt).group(1))
        for t in fam("chained_concrete"):
            L, W = map(int, re.search(r"footprint (\d+) ft × (\d+) ft", t.prompt).groups())
            slab = num(r"Slab on grade (\d+) in", t)
            fw, fd = map(float, re.search(r"footing ([\d.]+) ft wide × ([\d.]+) ft deep", t.prompt).groups())
            n, pad, pd = re.search(r"(\d+) column pads, each (\d+) ft × \d+ ft × ([\d.]+) ft", t.prompt).groups()
            n, pad, pd = int(n), int(pad), float(pd)
            waste = num(r"Add (\d+)% waste", t) / 100
            cy = math.ceil((L * W * slab / 12 + 2 * (L + W) * fw * fd + n * pad * pad * pd) / 27 * (1 + waste) * 2) / 2
            rate = num(r"concrete \$(\d+)/CY", t)
            lb, lbr = re.search(r"rebar (\d+) lb per CY at \$([\d.]+)/lb", t.prompt).groups()
            form = num(r"at \$([\d.]+) per sq ft of contact", t)
            crew, prod = re.search(r"placing crew \$(\d+)/hour at ([\d.]+) CY per crew-hour", t.prompt).groups()
            forms_sf = 4 * (L + W) * fd + n * 4 * pad * pd
            direct = cy * rate + cy * int(lb) * float(lbr) + forms_sf * form + cy / float(prod) * int(crew)
            gc, oh, pr = (num(p, t) / 100 for p in (r"general conditions (\d+)%", r"then overhead (\d+)%", r"then profit (\d+)%"))
            bond = num(r"then bond ([\d.]+)%", t) / 100
            bid = direct * (1 + gc) * (1 + oh) * (1 + pr) * (1 + bond)
            fdays, perday, cure, strip = re.search(r"forms (\d+) days, then pours at (\d+) CY per day.*?cure (\d+) days, "
                                                   r"then strip and backfill (\d+) days", t.prompt).groups()
            dur = int(fdays) + math.ceil(cy / int(perday)) + int(cure) + int(strip)
            ret = num(r"withholds (\d+)% retainage", t) / 100
            months = math.ceil(dur / 20)
            cum, worst = 0.0, 0.0
            for m in range(1, months + 2):
                cum -= direct / months if m <= months else 0
                cum += bid / months * (1 - ret) if m >= 2 else 0
                worst = min(worst, cum)
            self.assertAlmostEqual(t.answer["concrete_order_cy"], cy)
            self.assertAlmostEqual(t.answer["direct_cost"], direct, places=1)
            self.assertAlmostEqual(t.answer["bid_price"], bid, delta=0.02)
            self.assertEqual(t.answer["duration_workdays"], dur)
            self.assertAlmostEqual(t.answer["peak_cash_deficit"], worst, delta=0.05)

    def test_chain_overrides_carry_an_upstream_error_forward(self):
        t = fam("chained_concrete", seeds=(1,), n=1)[0]
        p = t.meta["params"]
        right = chain_values(p)
        self.assertEqual(right, t.answer)
        wrong_cy = right["concrete_order_cy"] + 20
        carried = chain_values(p, {"concrete_order_cy": wrong_cy})
        self.assertEqual(carried["concrete_order_cy"], wrong_cy)
        self.assertGreater(carried["direct_cost"], right["direct_cost"])
        self.assertGreater(carried["bid_price"], right["bid_price"])
        # a downstream answer can now be judged against the model's own upstream value
        self.assertEqual(chain_values(p, {"direct_cost": right["direct_cost"]})["bid_price"], right["bid_price"])


if __name__ == "__main__":
    unittest.main()
