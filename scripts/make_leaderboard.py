#!/usr/bin/env python3
"""Writes docs/LEADERBOARD.md from the tracked results in paper/report/runs.csv. No dependencies.
Run: python3 scripts/make_leaderboard.py"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rows = list(csv.DictReader(open(ROOT / "paper" / "report" / "runs.csv", encoding="utf-8", newline="")))
COND = {"base": "No harness", "harness": "Code tool + strict answer"}
sets = {}
for r in rows:
    sets.setdefault(r["set"], []).append(r)

def pct(x):
    return f"{float(x) * 100:.1f}%"

def money(x, places=2):
    return f"${float(x):.{places}f}" if x not in ("", None) else "n/a"

out = ["# Results", "",
       "Generated from [`paper/report/runs.csv`](../paper/report/runs.csv) by `scripts/make_leaderboard.py`. Every row is a model run on a fixed, seeded task set;",
       "accuracy is **strict** (every field of the answer must be right) with a 95% Wilson interval. Read the caveats at the bottom before quoting a number.", ""]
for name in sorted(sets):
    group = sets[name]
    out += [f"## {name}", "", "| Model | Condition | Tasks run | Strict accuracy (95% CI) | Field score | Cost | $ per correct |", "|---|---|---|---|---|---|---|"]
    for r in sorted(group, key=lambda r: (r["model"], r["condition"])):
        done = f"{r['runs']} of {r['tasks']}" if r["runs"] != r["tasks"] else r["tasks"]
        out.append(f"| {r['model']} | {COND.get(r['condition'], r['condition'])} | {done} | {pct(r['accuracy'])} ({pct(r['ci_lo'])} to {pct(r['ci_hi'])}) | {pct(r['field_score'])} | {money(r['cost_usd']) if r['cost_usd'] else 'n/a'} | {money(r['cost_per_correct'], 4) if r['cost_per_correct'] else 'n/a'} |")
    out.append("")
out += ["## Caveats", "",
        "- **Frontier models are at the ceiling on the original sets.** Claude Opus, Sonnet and Haiku score at or near 100% on `quick-families` and `fresh-*`, so those sets cannot separate them. The harder expert sets, and the families still being added, exist for that reason.",
        "- **Incomplete runs are not failures.** Where \"Tasks run\" is lower than the set size, the run stopped (a cost cap or a rate limit) and the missing tasks are reported as not run, never as wrong. Treat those rows as partial; the wide intervals show it.",
        "- **`quick-families` is a development set.** It was used while the harness was being built, so it is not a clean test of anything. `fresh-*` and `expert*` sets were generated afterwards.",
        "- **One seed per set.** A different seed gives different numbers; the intervals cover task sampling within a set, not seed-to-seed variation.",
        "- **Costs are client-side estimates** from token counts and list prices. DeepSeek rows have no cost: its spend was measured as an account balance change, not per task.",
        "- **Held-out sets are private.** The sets used to check a model that may have trained on public items are not in this repository.", "",
        "Add your own run with `python -m constructbench run ...` and `leaderboard` (see the README). Open a pull request with the result file and the exact command."]
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "LEADERBOARD.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("wrote docs/LEADERBOARD.md")
