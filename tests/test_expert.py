"""Expert tier: every answer re-derived from the prompt text alone, with code written separately from the generators.

If a generator's reference answer and this independent reading of its own prompt disagree, either the prompt
under-specifies the task or the reference is wrong — both are benchmark bugs.
"""
import datetime as dt
import math
import re
import unittest

from constructbench import registry
from constructbench.agent import answer_keys
from constructbench.grading import grade
from constructbench.providers import Oracle

FAMS = ["pdm_calendar", "pay_app_certification", "wip_portfolio", "cost_ledger", "mass_haul", "delay_tia",
        "bid_leveling_expert"]


def fam(name, seeds=(1, 2, 3), n=8):
    return [t for s in seeds for t in registry.build(seed=s, per_family=n, families=[name])]


def rows(prompt, start_marker=None):
    text = prompt if start_marker is None else prompt[prompt.index(start_marker):]
    out, started = [], False
    for line in text.splitlines():
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
    s = s.strip().replace("$", "").replace(",", "")
    return float(s)


def iso(s):
    return dt.date.fromisoformat(s)


class Expert(unittest.TestCase):
    def test_every_family_is_expert_and_oracle_passes(self):
        for name in FAMS:
            for t in fam(name, seeds=(1,), n=5):
                self.assertEqual(t.difficulty, "expert")
                self.assertTrue(grade(t, Oracle().answer(t).text).correct, t.id)
                # the harness must be able to read every answer key from the prompt
                self.assertEqual([k for k, _ in answer_keys(t.prompt)], list(t.fields), t.id)

    def test_same_seed_same_tasks(self):
        a = registry.build(seed=5, per_family=2, families=FAMS)
        b = registry.build(seed=5, per_family=2, families=FAMS)
        self.assertEqual([t.to_json() for t in a], [t.to_json() for t in b])

    def test_pdm_from_prompt(self):
        for t in fam("pdm_calendar"):
            acts = rows(t.prompt, "| ID |")
            ids = [r[0] for r in acts]
            dur = {r[0]: int(r[2]) for r in acts}
            rel = {}
            for r in acts:
                rel[r[0]] = [] if r[3] == "—" else [
                    (m.group(1), m.group(2), int(m.group(3) or 0))
                    for m in re.finditer(r"(A\d+) (FS|SS|FF)(?:\+(\d+))?", r[3])]
            es, ef = {}, {}
            for a in ids:                      # ids are listed in an order where predecessors come first
                lo = 0
                for p, kind, lag in rel[a]:
                    if kind == "FS":
                        lo = max(lo, ef[p] + lag)
                    elif kind == "SS":
                        lo = max(lo, es[p] + lag)
                    else:
                        lo = max(lo, ef[p] + lag - dur[a])
                es[a] = lo
                ef[a] = lo + dur[a]
            T = max(ef.values())
            lf = {a: T for a in ids}
            ls = {}
            for a in reversed(ids):
                for b in ids:
                    for p, kind, lag in rel[b]:
                        if p != a:
                            continue
                        if kind == "FS":
                            lf[a] = min(lf[a], ls[b] - lag)
                        elif kind == "SS":
                            lf[a] = min(lf[a], ls[b] - lag + dur[a])
                        else:
                            lf[a] = min(lf[a], lf[b] - lag)
                ls[a] = lf[a] - dur[a]
            start = iso(re.search(r"day 0 is (\d{4}-\d\d-\d\d)", t.prompt).group(1))
            hol = {iso(h) for h in re.findall(r"\d{4}-\d\d-\d\d",
                                                re.search(r"except these holidays: ([^.]*)\.", t.prompt).group(1))}
            days, d = [], start
            while len(days) <= T:
                if d.weekday() < 5 and d not in hol:
                    days.append(d)
                d += dt.timedelta(days=1)
            self.assertEqual(t.answer["project_duration_workdays"], T)
            self.assertEqual(t.answer["project_finish_date"], days[T - 1].isoformat())
            self.assertEqual(set(t.answer["critical_activities"]), {a for a in ids if ls[a] == es[a]})
            for k, v in t.answer.items():
                if k.startswith("total_float_"):
                    self.assertEqual(v, ls[k[12:]] - es[k[12:]])
                if k.startswith("early_start_date_"):
                    self.assertEqual(v, days[es[k[17:]]].isoformat())

    def test_pay_app_from_prompt(self):
        saw_rate = set()
        for t in fam("pay_app_certification"):
            lines = rows(t.prompt, "| Item |")
            errs, excl, G, DE, F, C, D_prev = [], [], 0.0, 0.0, 0.0, 0.0, 0.0
            for item, desc, c, d, e, f, g, h in lines:
                c, d, e, f, g, h = map(dollars, (c, d, e, f, g, h))
                if "pending" in desc:
                    excl.append(item)
                    continue
                if g != d + e + f or h != c - (d + e + f):
                    errs.append(item)
                C += c; DE += d + e; F += f; G += d + e + f
            rate = 0.05 if G / C > 0.5 else 0.10
            saw_rate.add(rate)
            prev = dollars(re.search(r"Previous certificates for payment total (\$[\d,]+)", t.prompt).group(1))
            ret = rate * DE + 0.10 * F
            self.assertEqual(set(t.answer["error_lines"]), set(errs))
            self.assertEqual(set(t.answer["excluded_lines"]), set(excl))
            self.assertAlmostEqual(t.answer["corrected_total_completed_stored"], G, places=2)
            self.assertAlmostEqual(t.answer["retainage"], ret, places=2)
            self.assertAlmostEqual(t.answer["current_payment_due"], G - ret - prev, places=2)
        self.assertEqual(saw_rate, {0.05, 0.10})               # both sides of the 50% rule occur

    def test_pay_app_hard_from_prompt(self):
        """Second level: the interacting traps must be re-derivable from the prompt alone — unapproved stored
        materials out of every total (rule 3), pending billings already inside the previous certificates (rule 6),
        and a deductive change order carried with its sign (rule 4)."""
        saw_rate, saw_unapproved = set(), 0
        for t in fam("pay_app_certification_hard"):
            errs, excl, unapproved = [], [], []
            sumC = sumDE = sumF = 0.0
            for item, desc, c, d, e, f, ok, g, h in rows(t.prompt, "| Item |"):
                c, d, e, f, g, h = map(dollars, (c, d, e, f, g, h))
                if "pending" in desc:
                    excl.append(item)
                    continue
                if g != d + e + f or h != c - (d + e + f):
                    errs.append(item)
                if f > 0 and ok == "N":
                    unapproved.append(item)
                sumC += c
                sumDE += d + e
                sumF += f if ok == "Y" else 0.0
            sumG = sumDE + sumF
            rate = 0.05 if sumG / sumC > 0.5 else 0.10
            saw_rate.add(rate)
            prev = dollars(re.search(r"Previous certificates for payment total (\$[\-\d,]+)", t.prompt).group(1))
            on_pending = dollars(re.search(r"already includes (\$[\-\d,]+) billed on the pending items",
                                           t.prompt).group(1))
            prev_adj = prev - on_pending
            ret = rate * sumDE + 0.10 * sumF
            saw_unapproved += 1 if unapproved else 0
            self.assertEqual(set(t.answer["error_lines"]), set(errs), t.id)
            self.assertEqual(set(t.answer["excluded_lines"]), set(excl), t.id)
            self.assertEqual(set(t.answer["unapproved_stored_lines"]), set(unapproved), t.id)
            self.assertAlmostEqual(t.answer["corrected_total_completed_stored"], sumG, places=2)
            self.assertAlmostEqual(t.answer["retainage"], ret, places=2)
            self.assertAlmostEqual(t.answer["previous_certificates_adjusted"], prev_adj, places=2)
            self.assertAlmostEqual(t.answer["current_payment_due"], sumG - ret - prev_adj, places=2)
        self.assertEqual(saw_unapproved, len(fam("pay_app_certification_hard")))   # every item carries the trap
        self.assertEqual(saw_rate, {0.05, 0.10})                                   # the knife-edge is exercised

    def test_delay_tia_hard_from_prompt(self):
        """Second level: the monthly weather allowance, the two notice periods and the two caps must all be
        re-derivable from the prompt text alone."""
        capped_ld = capped_gc = 0
        for t in fam("delay_tia_hard"):
            p = t.prompt
            original = dt.date.fromisoformat(re.search(r"contract completion date (\d{4}-\d{2}-\d{2})", p).group(1))
            actual = dt.date.fromisoformat(re.search(r"Actual substantial completion: (\d{4}-\d{2}-\d{2})", p).group(1))
            rate = dollars(re.search(r"liquidated damages (\$[\d,]+) per calendar day", p).group(1))
            cap_pct = float(re.search(r"capped at ([\d.]+)% of", p).group(1))
            sum_ = dollars(re.search(r"contract sum (\$[\d,]+)", p).group(1))
            gc_rate = dollars(re.search(r"recoverable at (\$[\d,]+) per compensable day", p).group(1))
            gc_cap = dollars(re.search(r"capped at (\$[\d,]+)\. Actual", p).group(1))
            anticipated = {m: int(n) for m, n in
                           re.findall(r"(\d{4}-\d{2}) (\d+)", re.search(r"by calendar month: ([^.]+)\.", p).group(1))}
            live = []
            for _e, _desc, who, s, f, crit, notice in rows(p, "| Event |"):
                s, f, notice = (dt.date.fromisoformat(x) for x in (s, f, notice))
                if crit == "Yes" and (who == "Contractor" or (notice - s).days <= (21 if who == "Owner" else 10)):
                    live.append((who, s, f))                    # rule 2: two notice periods
            exc = comp = disallowed = 0
            used: dict[str, int] = {}
            d = min(w[1] for w in live)
            last = max(w[2] for w in live)
            while d <= last:
                who = {w[0] for w in live if w[1] <= d <= w[2]}
                if who and who != {"Contractor"}:
                    if who == {"Owner"}:
                        exc += 1
                        comp += 1
                    elif who == {"Weather"}:                    # rule 4: the monthly allowance
                        m = d.strftime("%Y-%m")
                        used[m] = used.get(m, 0) + 1
                        if used[m] > anticipated[m]:
                            exc += 1
                        else:
                            disallowed += 1
                    else:
                        exc += 1
                d += dt.timedelta(days=1)
            extended = original + dt.timedelta(days=exc)
            ld_days = max(0, (actual - extended).days)
            ld_amount = min(ld_days * rate, sum_ * cap_pct / 100.0)           # rule 6: capped
            gc_cost = min(comp * gc_rate, gc_cap)                             # rule 7: capped
            capped_ld += 1 if ld_days * rate > sum_ * cap_pct / 100.0 else 0
            capped_gc += 1 if comp * gc_rate > gc_cap else 0
            self.assertEqual(t.answer["extension_days"], exc, t.id)
            self.assertEqual(t.answer["compensable_days"], comp, t.id)
            self.assertEqual(t.answer["extended_completion_date"], extended.isoformat(), t.id)
            self.assertEqual(t.answer["ld_days"], ld_days, t.id)
            self.assertAlmostEqual(t.answer["ld_amount"], round(ld_amount, 2), places=2)
            self.assertAlmostEqual(t.answer["extended_general_conditions_cost"], round(gc_cost, 2), places=2)
            self.assertEqual(t.answer["weather_days_not_excusable"], disallowed, t.id)
        self.assertGreater(capped_ld, 0)      # the liquidated-damages cap binds on at least one item
        self.assertGreater(capped_gc, 0)      # and so does the general-conditions cap

    def test_bid_leveling_hard_from_prompt(self):
        """Second level: the rejected non-responsive bid and the unit-price correction must both be re-derived from
        the prompt, and each must actually change the top two — a model that misses either names a different winner."""
        num = {w: k for k, w in enumerate(["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
                                           "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
                                           "sixteen", "seventeen", "eighteen", "nineteen"])}
        num.update({w: 10 * k for k, w in enumerate(["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
                                                     "eighty", "ninety"]) if w})

        def parse_words(text):
            total = cur = 0
            for w in text.replace("-", " ").split():
                if w in num:
                    cur += num[w]
                elif w == "hundred":
                    cur *= 100
                elif w in ("thousand", "million"):
                    total += cur * (1000 if w == "thousand" else 1_000_000)
                    cur = 0
            return total + cur

        for t in fam("bid_leveling_expert_hard"):
            p = t.prompt
            bond = float(re.search(r"bond has ([\d.]+)% added", p).group(1)) / 100
            mandatory = re.search(r"every one\): (.+)", p).group(1).split(", ")
            forms = re.findall(r"- (.+?): base bid in figures (\$[\d,]+); in words \"(.+?) dollars\"(.*?); bond "
                               r"(included|NOT included); .*?: add (\$[\d,]+)", p)
            table = rows(p, "| Scope item |")
            plugs = {r[0]: dollars(r[1]) for r in table}
            names = [f[0] for f in forms]

            def leveled(apply2=True, apply3=True):
                out, rejected = {}, []
                for name, figures, wds, mid, b, alt in forms:
                    col = names.index(name) + 2
                    sts = {r[0]: r[col] for r in table}
                    if apply3 and any(sts[m] == "Excl" for m in mandatory):
                        rejected.append(name)
                        continue
                    base = parse_words(wds)
                    lt = re.search(r"line items total (\$[\d,]+)", mid)
                    if apply2 and lt and "unit prices govern" in mid:
                        base = dollars(lt.group(1))
                    total = base + dollars(alt)
                    for it, st in sts.items():
                        if st == "Excl":
                            total += plugs[it]
                        elif st.startswith("Allow"):
                            total += max(0.0, plugs[it] - dollars(st.split("$")[1]))
                    if b == "NOT included":
                        total *= 1 + bond
                    out[name] = total
                return out, rejected

            lev, rej = leveled()
            order = sorted(lev, key=lev.get)
            self.assertEqual(t.answer["low_bidder"], order[0], t.id)
            self.assertAlmostEqual(t.answer["low_leveled_amount"], round(lev[order[0]], 2), places=2)
            self.assertAlmostEqual(t.answer["second_leveled_amount"], round(lev[order[1]], 2), places=2)
            self.assertEqual(set(t.answer["rejected_bidders"]), set(rej), t.id)
            self.assertAlmostEqual(t.answer["leveled_spread"],
                                  round(max(lev.values()) - min(lev.values()), 2), places=2)
            naive2, _ = leveled(apply2=False)
            self.assertNotEqual(sorted(naive2, key=naive2.get)[:2], order[:2], t.id)   # rule 2 matters
            naive3, _ = leveled(apply3=False)
            self.assertIn(sorted(naive3, key=naive3.get)[0], rej, t.id)                # the rejection matters

    def test_wip_from_prompt(self):
        for t in fam("wip_portfolio"):
            over = under = prov = gp = 0.0
            unders = {}
            for job, status, c, e, d, b in rows(t.prompt, "| Job |"):
                if status != "Open":
                    continue
                c, e, d, b = map(dollars, (c, e, d, b))
                poc = d / e
                earned = poc * c
                if b > earned:
                    over += b - earned
                else:
                    under += earned - b
                    unders[job] = earned - b
                p = (e - c) * (1 - poc) if e > c else 0.0
                prov += p
                gp += earned - d - p
            self.assertAlmostEqual(t.answer["billings_in_excess_total"], over, places=1)
            self.assertAlmostEqual(t.answer["costs_in_excess_total"], under, places=1)
            self.assertAlmostEqual(t.answer["provision_for_losses"], prov, places=1)
            self.assertAlmostEqual(t.answer["gross_profit_to_date"], gp, places=1)
            self.assertEqual(t.answer["most_underbilled_job"], max(unders, key=unders.get))

    def test_ledger_from_prompt(self):
        for t in fam("cost_ledger"):
            job = re.search(r"for job (J-\d+) from", t.prompt).group(1)
            cutoff = iso(re.search(r"cut-off date (\d{4}-\d\d-\d\d)", t.prompt).group(1))
            asked = re.search(r"on cost code (\d\d-\d{3})", t.prompt).group(1)
            csv = re.search(r"```csv\n(.*?)```", t.prompt, re.S).group(1).strip().splitlines()[1:]
            recs = [l.split(",") for l in csv]
            mine = [r for r in recs if r[1] == job and iso(r[0]) <= cutoff]
            voided = {(r[3], r[4]) for r in mine if r[6] == "VOID"}
            seen, dup, by = set(), 0, {}
            for date, _, code, vendor, doc, amt, kind in mine:
                if kind == "VOID":
                    continue
                if kind == "INV":
                    if (vendor, doc, amt) in seen:
                        dup += 1
                        continue
                    seen.add((vendor, doc, amt))
                    if (vendor, doc) in voided:
                        continue
                by[code] = by.get(code, 0.0) + float(amt)
            budgets = {r[0].split()[0]: dollars(r[1]) for r in rows(t.prompt, "| Cost code |")}
            over = {c: by.get(c, 0.0) - b for c, b in budgets.items()}
            worst = max(over, key=over.get)
            self.assertAlmostEqual(t.answer["total_cost_to_date"], sum(by.values()), places=2)
            self.assertAlmostEqual(t.answer["asked_code_cost"], by[asked], places=2)
            self.assertEqual(t.answer["duplicate_rows_removed"], dup)
            self.assertEqual(t.answer["largest_overrun_code"], worst)
            self.assertAlmostEqual(t.answer["largest_overrun_amount"], over[worst], places=2)
            self.assertGreater(dup, 0)

    def test_mass_haul_from_prompt(self):
        for t in fam("mass_haul"):
            st = rows(t.prompt, "| Station |")
            step = int(re.search(r"every (\d+) ft", t.prompt).group(1))
            s = int(re.search(r"Shrinkage is (\d+)%", t.prompt).group(1)) / 100
            cut = fill = m = 0.0
            ords = [0.0]
            for (_, c1, f1), (_, c2, f2) in zip(st, st[1:]):
                cv = (float(c1) + float(c2)) / 2 * step / 27
                fv = (float(f1) + float(f2)) / 2 * step / 27
                cut += cv; fill += fv
                m += cv * (1 - s) - fv
                ords.append(m)
            k = max(range(len(ords)), key=lambda j: ords[j])
            self.assertAlmostEqual(t.answer["total_cut_bcy"], cut, places=1)
            self.assertAlmostEqual(t.answer["total_fill_ccy"], fill, places=1)
            self.assertAlmostEqual(t.answer["net_bcy"], ords[-1] / (1 - s), places=1)
            self.assertAlmostEqual(t.answer["max_ordinate_ccy"], ords[k], places=1)
            self.assertEqual(t.answer["max_ordinate_station"], st[k][0])

    def test_tia_from_prompt(self):
        for t in fam("delay_tia"):
            orig = iso(re.search(r"contract completion date (\d{4}-\d\d-\d\d)", t.prompt).group(1))
            actual = iso(re.search(r"Actual substantial completion: (\d{4}-\d\d-\d\d)", t.prompt).group(1))
            rate = dollars(re.search(r"liquidated damages (\$[\d,]+) per", t.prompt).group(1))
            evs = []
            for e, desc, who, s, f, crit, notice in rows(t.prompt, "| Event |"):
                if crit != "Yes":
                    continue
                if who != "Contractor" and (iso(notice) - iso(s)).days > 21:
                    continue
                evs.append((who, iso(s), iso(f)))
            days = {}
            for who, s, f in evs:
                d = s
                while d <= f:
                    days.setdefault(d, set()).add(who)
                    d += dt.timedelta(days=1)
            exc = sum(1 for w in days.values() if w != {"Contractor"})
            comp = sum(1 for w in days.values() if w == {"Owner"})
            ext = orig + dt.timedelta(days=exc)
            ld = max(0, (actual - ext).days)
            self.assertEqual((t.answer["extension_days"], t.answer["compensable_days"]), (exc, comp))
            self.assertEqual(t.answer["extended_completion_date"], ext.isoformat())
            self.assertEqual((t.answer["ld_days"], t.answer["ld_amount"]), (ld, ld * rate))

    def test_bid_leveling_from_prompt(self):
        num = {w: k for k, w in enumerate(["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                                           "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
                                           "seventeen", "eighteen", "nineteen"])}
        num.update({w: 10 * k for k, w in enumerate(["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
                                                     "eighty", "ninety"]) if w})

        def parse_words(text):
            total = cur = 0
            for w in text.replace("-", " ").split():
                if w in num:
                    cur += num[w]
                elif w == "hundred":
                    cur *= 100
                elif w in ("thousand", "million"):
                    total += cur * (1000 if w == "thousand" else 1_000_000)
                    cur = 0
            return total + cur

        trap = 0
        for t in fam("bid_leveling_expert"):
            bond = float(re.search(r"gets ([\d.]+)% added", t.prompt).group(1)) / 100
            forms = re.findall(r"- (.+?): base bid in figures (\$[\d,]+); in words \"(.+?) dollars\"; bond (included|NOT "
                               r"included); .*?: add (\$[\d,]+)", t.prompt)
            table = rows(t.prompt, "| Scope item |")
            names = [f[0] for f in forms]
            lev, fig = {}, {}
            for k, (name, figures, wds, b, alt) in enumerate(forms):
                total = parse_words(wds) + dollars(alt)
                fig[name] = dollars(figures)
                for r in table:
                    plug, status = dollars(r[1]), r[2 + k]
                    if status == "Excl":
                        total += plug
                    elif status.startswith("Allow"):
                        total += max(0.0, plug - dollars(status.split()[1]))
                if b == "NOT included":
                    total *= 1 + bond
                lev[name] = total
            order = sorted(names, key=lev.get)
            self.assertEqual(t.answer["low_bidder"], order[0])
            self.assertAlmostEqual(t.answer["low_leveled_amount"], lev[order[0]], places=1)
            self.assertAlmostEqual(t.answer["second_leveled_amount"], lev[order[1]], places=1)
            trap += min(fig, key=fig.get) != order[0]
        self.assertGreater(trap, 0)                          # the lowest figure is sometimes not the low bidder


if __name__ == "__main__":
    unittest.main()
