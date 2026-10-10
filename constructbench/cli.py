"""ConstructBench command line.

  python -m constructbench generate --seed 1 --per-family 5 --out data/dev.jsonl
  python -m constructbench run --tasks data/dev.jsonl --provider anthropic:claude-opus-5 --out results/opus5.jsonl
  python -m constructbench score results/opus5.jsonl --tasks data/dev.jsonl
  python -m constructbench leaderboard results/*.jsonl --tasks data/dev.jsonl --out results/LEADERBOARD.md
  python -m constructbench show data/dev.jsonl vis-plan-0000 --save-images out/
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

from . import registry
from .providers import make
from .runner import load_tasks, save_tasks, run, regrade, summarize
from .task import DOMAINS


# Column labels for tables; any domain without one falls back to its name, so a new domain can't break a report.
SHORT = {"architecture": "Arch", "design": "Design", "estimating": "Estim", "preconstruction": "Precon",
         "scheduling": "Sched", "project_management": "PM", "finance": "Finance", "document_recognition": "Docs",
         "visual_intelligence": "Visual", "safety": "Safety", "robotics": "Robotics",
         "civil": "Civil", "sustainability": "Sustain", "real_estate": "RE & FM",
         "quality": "QC", "contracts": "Contracts"}


def short(d: str) -> str:
    return SHORT.get(d, d)


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def cmd_generate(a):
    tasks = registry.build(a.seed, a.per_family, a.domain or None, a.family or None)
    save_tasks(tasks, Path(a.out))
    counts = {}
    for t in tasks:
        counts[t.domain] = counts.get(t.domain, 0) + 1
    print(f"{len(tasks)} tasks → {a.out}")
    for d, n in counts.items():
        print(f"  {d:22s} {n}")


def cmd_run(a):
    tasks = load_tasks(Path(a.tasks))
    run(make(a.provider, a.effort), tasks, Path(a.out), workers=a.workers)
    cmd_score(argparse.Namespace(results=a.out, tasks=a.tasks, json=False))


def cmd_score(a):
    rows = regrade(Path(a.results), load_tasks(Path(a.tasks)))
    s = summarize(rows)
    if a.json:
        print(json.dumps(s, indent=1)); return
    o = s["overall"]
    print(f"{Path(a.results).name}: {o['correct']}/{o['n']} fully correct = {_pct(o['accuracy'])} "
          f"(95% CI {_pct(o['ci95'][0])}–{_pct(o['ci95'][1])}), field score {_pct(o['field_score'])}")
    for d, v in s["domains"].items():
        print(f"  {d:22s} {_pct(v['accuracy']):>7s}  ({v['correct']}/{v['n']}; fields {_pct(v['field_score'])}; "
              f"{v['mean_seconds']:.1f}s/task)")
    print("  by difficulty: " + ", ".join(f"{d} {_pct(v['accuracy'])} ({v['correct']}/{v['n']})" for d, v in s["difficulty"].items()))


def cmd_leaderboard(a):
    tasks = load_tasks(Path(a.tasks))
    runs = []
    for p in a.results:
        rows = regrade(Path(p), tasks)
        if rows:
            runs.append((rows[0]["provider"], summarize(rows)))
    runs.sort(key=lambda r: r[1]["overall"]["accuracy"], reverse=True)
    doms = [d for d in DOMAINS if any(d in s["domains"] for _, s in runs)]
    lines = ["# ConstructBench leaderboard", "", f"Task set: `{Path(a.tasks).name}` · {len(tasks)} tasks · accuracy = every field right", "",
             "| Model | Overall | " + " | ".join(short(d) for d in doms) + " |", "|---|---|" + "---|" * len(doms)]
    for name, s in runs:
        o = s["overall"]
        cells = [(_pct(s["domains"][d]["accuracy"]) if d in s["domains"] else "—") for d in doms]
        lines.append(f"| {name} | **{_pct(o['accuracy'])}** ({o['n']}) | " + " | ".join(cells) + " |")
    lines += ["", "Domains: " + "; ".join(f"**{short(d)}** — {DOMAINS[d]}" for d in doms)]
    text = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).write_text(text)
    print(text)


def cmd_compare(a):
    """Two runs side by side on the tasks both answered: per-domain accuracy, the gap, and where they disagree."""
    tasks = load_tasks(Path(a.tasks))
    ra, rb = regrade(Path(a.a), tasks), regrade(Path(a.b), tasks)
    ga = {r["task_id"]: r for r in ra}
    gb = {r["task_id"]: r for r in rb}
    both = sorted(set(ga) & set(gb))
    na, nb = ra[0]["provider"] if ra else a.a, rb[0]["provider"] if rb else a.b
    sa, sb = summarize([ga[i] for i in both]), summarize([gb[i] for i in both])
    only_a = [i for i in both if ga[i]["grade"]["correct"] and not gb[i]["grade"]["correct"]]
    only_b = [i for i in both if gb[i]["grade"]["correct"] and not ga[i]["grade"]["correct"]]
    lines = [f"# {na} vs {nb}", "", f"{len(both)} tasks answered by both (of {len(tasks)} in `{Path(a.tasks).name}`).", "",
             f"| Domain | {na} | {nb} | Gap |", "|---|---|---|---|"]
    def row(label, x, y):
        gap = (x["accuracy"] - y["accuracy"]) * 100
        return f"| {label} | {_pct(x['accuracy'])} ({x['correct']}/{x['n']}) | {_pct(y['accuracy'])} ({y['correct']}/{y['n']}) | {gap:+.1f} pts |"
    lines.append(row("**Overall**", sa["overall"], sb["overall"]))
    for d in DOMAINS:
        if d in sa["domains"]:
            lines.append(row(DOMAINS[d].split(" — ")[0], sa["domains"][d], sb["domains"][d]))
    lines += ["", "| Difficulty | " + na + " | " + nb + " | Gap |", "|---|---|---|---|"]
    for d in sa["difficulty"]:
        lines.append(row(d.capitalize(), sa["difficulty"][d], sb["difficulty"][d]))
    lines += ["", f"Mean time per task: {na} {sa['overall']['mean_seconds']:.1f}s · {nb} {sb['overall']['mean_seconds']:.1f}s"]
    lines += ["", f"Only {na} right: {len(only_a)} · only {nb} right: {len(only_b)} · both right: "
              f"{sum(1 for i in both if ga[i]['grade']['correct'] and gb[i]['grade']['correct'])} · both wrong: "
              f"{sum(1 for i in both if not ga[i]['grade']['correct'] and not gb[i]['grade']['correct'])}"]
    skipped = sorted(set(ga) ^ set(gb))
    if skipped:
        lines.append(f"Not compared (answered by only one run, e.g. image tasks for a text-only model): {len(skipped)}")
    text = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).write_text(text)
    print(text)


def cmd_show(a):
    t = next((t for t in load_tasks(Path(a.tasks)) if t.id == a.id), None)
    if not t:
        sys.exit(f"no task {a.id}")
    print(f"[{t.domain} / {t.category} / {t.difficulty}] {t.title}\n\n{t.prompt}\n\nReference: {json.dumps(t.answer)}")
    if a.save_images and t.attachments:
        d = Path(a.save_images); d.mkdir(parents=True, exist_ok=True)
        for att in t.attachments:
            (d / att["name"]).write_bytes(base64.b64decode(att["data"]))
            print(f"image → {d / att['name']}")


def cmd_decontam(a):
    from . import decontam
    report = decontam.check(load_tasks(Path(a.tasks)), [Path(p) for p in a.corpus], a.n, a.min_numbers, a.run, a.coverage)
    print(json.dumps(report if a.ids else {k: v for k, v in report.items() if k != "task_ids"}, indent=2))
    if a.fail_over is not None and report["contaminated_rate"] > a.fail_over:
        raise SystemExit(f"contaminated: {report['contaminated']} of {report['tasks']} tasks appear in the corpus")


def main(argv=None):
    p = argparse.ArgumentParser(prog="constructbench", description="Benchmark AI models on construction work.")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate"); g.add_argument("--seed", type=int, default=1); g.add_argument("--per-family", type=int, default=5)
    g.add_argument("--domain", action="append"); g.add_argument("--family", action="append"); g.add_argument("--out", default="data/dev.jsonl")
    g.set_defaults(fn=cmd_generate)
    r = sub.add_parser("run"); r.add_argument("--tasks", required=True); r.add_argument("--provider", required=True)
    r.add_argument("--out", required=True); r.add_argument("--effort", default="high"); r.add_argument("--workers", type=int, default=4)
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("score"); s.add_argument("results"); s.add_argument("--tasks", required=True); s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_score)
    lb = sub.add_parser("leaderboard"); lb.add_argument("results", nargs="+"); lb.add_argument("--tasks", required=True); lb.add_argument("--out")
    lb.set_defaults(fn=cmd_leaderboard)
    cp = sub.add_parser("compare"); cp.add_argument("a"); cp.add_argument("b"); cp.add_argument("--tasks", required=True); cp.add_argument("--out")
    cp.set_defaults(fn=cmd_compare)
    sh = sub.add_parser("show"); sh.add_argument("tasks"); sh.add_argument("id"); sh.add_argument("--save-images")
    sh.set_defaults(fn=cmd_show)
    dc = sub.add_parser("decontam", help="flag benchmark items that appear in a training corpus (numbers kept)")
    dc.add_argument("tasks"); dc.add_argument("corpus", nargs="+")
    dc.add_argument("--n", type=int, default=12); dc.add_argument("--min-numbers", type=int, default=3)
    dc.add_argument("--run", type=int, default=4, help="consecutive numbers that fingerprint an item")
    dc.add_argument("--coverage", type=float, default=0.5, help="share of a task's fingerprint that must appear to flag it")
    dc.add_argument("--ids", action="store_true", help="list the contaminated task ids")
    dc.add_argument("--fail-over", type=float, help="exit 1 when the contaminated rate is above this (CI gate)")
    dc.set_defaults(fn=cmd_decontam)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
