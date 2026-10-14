"""`constructbench report` — paper-ready tables and figures from result folders, in one command.

Reads every results/<set>/*.jsonl (manifests ignored), matching each folder to data/<set>.jsonl, and writes to the
output folder:
  report.md               every table below plus the figures, ready to lift into a paper
  runs.csv                one row per run file: model, condition, effort, set, tasks, runs, accuracy + Wilson CI,
                          field score, cost, cost per correct answer, output tokens, seconds
  paired.csv              each condition vs the same model's baseline (same set, effort): paired difference with
                          bootstrap CI, sign-flip and McNemar p (stats.paired)
  failures.csv            failure categories per run (see `classify`)
  fig_accuracy_<set>.svg  accuracy by model × condition with 95% CIs
  fig_size.svg            accuracy vs task size (prompt length bins), baseline vs harness, per model
  fig_failures.svg        failure categories per run (stacked)
  fig_pareto.svg          cost per task vs accuracy, with the cost-accuracy frontier
Figures are plain SVG (no dependencies), light, print-friendly; every mark carries a <title> with its numbers and
every series is labelled or in a legend (colour is never the only cue). Palette: the dataviz reference categorical
slots in fixed order, validated (scripts/validate_palette.js) for the four conditions.
"""
from __future__ import annotations

import csv
import html
import math
from pathlib import Path

from .grading import _to_number, extract_answer
from .runner import load_tasks, regrade, summarize, wilson
from .stats import paired

CONDITIONS = ["base", "code", "submit", "harness"]
LABEL = {"base": "No harness", "code": "Code only", "submit": "Submit only", "harness": "Harness (code + submit)"}
COLOR = {"harness": "#2a78d6", "base": "#eb6834", "code": "#1baf7a", "submit": "#eda100"}
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#fcfcfb"
FAILURE_ORDER = ["format: prose in ID list", "numeric error (>1%)", "near miss (≤1%)", "wrong value",
                 "no answer: out of tokens", "no answer: unparseable", "task-budget stop", "refusal", "API error"]
FAILURE_COLOR = dict(zip(FAILURE_ORDER, ["#eda100", "#e34948", "#e87ba4", "#6250d6", "#2a78d6", "#1baf7a", "#008300",
                                         "#52514e", "#8a8984"]))


def parse_provider(name: str) -> tuple[str, str, str]:
    """'anthropic:claude-haiku-5-5+code+submit@low' -> ('claude-haiku-5-5', 'harness', 'low')."""
    body, _, effort = name.partition("@")
    body = body.split(":", 1)[1] if ":" in body else body
    model, *flags = body.split("+")
    fl = set(flags) - {"images"}
    cond = "harness" if fl == {"code", "submit"} else "code" if fl == {"code"} else "submit" if fl == {"submit"} else "base"
    return model, cond, effort or ("high" if name.startswith("anthropic") else "—")


def classify(row: dict, task) -> str | None:
    """One failure category for a wrong run (None if correct), in this priority: refusal / API error / budget stop /
    no answer, then by the worst wrong field: prose where IDs were asked, numeric error > 1%, wrong non-numeric value,
    numeric near miss <= 1%."""
    g, resp = row["grade"], row["response"]
    if g["correct"]:
        return None
    if resp.get("error") == "refusal":
        return "refusal"
    if not resp.get("ok", True):
        return "API error"
    if resp.get("stop_reason") == "task_budget" and not g["parsed"]:
        return "task-budget stop"
    if not g["parsed"]:
        return "no answer: out of tokens" if resp.get("stop_reason") in ("max_tokens", "length") else "no answer: unparseable"
    got = extract_answer(resp.get("text") or "") or {}
    cats = set()
    for k, ok in (g.get("fields") or {}).items():
        if ok:
            continue
        spec, want, have = task.fields[k], task.answer.get(k), got.get(k)
        if spec.kind in ("set", "list") and isinstance(have, list) and any(len(str(x)) > 20 for x in have):
            cats.add("format: prose in ID list")
        elif spec.kind == "number" and _to_number(have) is not None and want:
            rel = abs(_to_number(have) - float(want)) / abs(float(want))
            cats.add("near miss (≤1%)" if rel <= 0.01 else "numeric error (>1%)")
        else:
            cats.add("wrong value")
    return next(c for c in FAILURE_ORDER if c in cats) if cats else "wrong value"


def load(results_dirs: list[Path], data_dir: Path) -> list[dict]:
    runs = []
    for d in results_dirs:
        tf = data_dir / f"{d.name}.jsonl"
        if not tf.exists():
            continue
        tasks = load_tasks(tf)
        by_id = {t.id: t for t in tasks}
        for f in sorted(d.glob("*.jsonl")):
            if f.name.endswith(".manifest.jsonl") or f.name.startswith("."):
                continue
            rows = regrade(f, tasks)
            if not rows:
                continue
            model, cond, effort = parse_provider(rows[0]["provider"])
            if model in ("oracle", "blank"):
                continue
            runs.append({"set": d.name, "file": f, "model": model, "cond": cond, "effort": effort, "rows": rows,
                         "tasks": by_id})
    return runs


def run_table(runs: list[dict]) -> list[dict]:
    out = []
    for r in runs:
        s = summarize(r["rows"])["overall"]
        costs = [(x["response"].get("extra") or {}).get("cost_usd") for x in r["rows"]]
        costs = [c for c in costs if c is not None]
        cost = sum(costs) if costs else None
        out.append({"set": r["set"], "model": r["model"], "condition": r["cond"], "effort": r["effort"],
                    "tasks": len({x["task_id"] for x in r["rows"]}), "runs": s["n"], "correct": s["correct"],
                    "accuracy": s["accuracy"], "ci_lo": s["ci95"][0], "ci_hi": s["ci95"][1],
                    "field_score": s["field_score"], "cost_usd": cost,
                    "cost_per_task": cost / s["n"] if cost is not None and s["n"] else None,
                    "cost_per_correct": cost / s["correct"] if cost is not None and s["correct"] else None,
                    "mean_output_tokens": s["mean_output_tokens"], "mean_seconds": s["mean_seconds"]})
    return out


def paired_table(runs: list[dict]) -> list[dict]:
    out = []
    base = {(r["set"], r["model"], r["effort"]): r for r in runs if r["cond"] == "base"}
    for r in runs:
        b = base.get((r["set"], r["model"], r["effort"]))
        if r["cond"] == "base" or b is None:
            continue
        st = paired(r["rows"], b["rows"])
        out.append({"set": r["set"], "model": r["model"], "effort": r["effort"], "condition": r["cond"],
                    "tasks": st["tasks"], "acc_condition": st["acc_a"], "acc_base": st["acc_b"], "diff": st["diff"],
                    "diff_ci_lo": st["diff_ci95"][0], "diff_ci_hi": st["diff_ci95"][1],
                    "condition_better": st["a_better_tasks"], "base_better": st["b_better_tasks"],
                    "p_sign_flip": st["p_sign_flip"], "p_mcnemar": st["p_mcnemar"],
                    "cost_per_correct_condition": st["cost_per_correct_a"], "cost_per_correct_base": st["cost_per_correct_b"]})
    return out


def failure_table(runs: list[dict]) -> list[dict]:
    out = []
    for r in runs:
        counts = {c: 0 for c in FAILURE_ORDER}
        for x in r["rows"]:
            c = classify(x, r["tasks"][x["task_id"]])
            if c:
                counts[c] += 1
        out.append({"set": r["set"], "model": r["model"], "condition": r["cond"], "effort": r["effort"],
                    "runs": len(r["rows"]), **counts})
    return out


# ---------------------------------------------------------------- SVG helpers

def _svg(w: int, h: int, body: list[str], title: str, desc: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'font-family="Inter, Helvetica, Arial, sans-serif" font-size="12">\n<title>{html.escape(title)}</title>\n'
            f'<desc>{html.escape(desc)}</desc>\n<rect width="{w}" height="{h}" fill="{SURFACE}"/>\n' + "\n".join(body)
            + "\n</svg>\n")


def _text(x, y, s, size=12, fill=INK2, anchor="start", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}">{html.escape(str(s))}</text>')


def _bar(x, y0, y1, w, color, tip):
    """A bar with a 4 px rounded data end, square at the baseline (y0 = baseline, y1 = value)."""
    top, h = min(y0, y1), abs(y0 - y1)
    r = min(4, h / 2, w / 2)
    if h < 0.5:
        return ""
    path = (f"M{x:.1f},{y0:.1f} V{top + r:.1f} Q{x:.1f},{top:.1f} {x + r:.1f},{top:.1f} H{x + w - r:.1f} "
            f"Q{x + w:.1f},{top:.1f} {x + w:.1f},{top + r:.1f} V{y0:.1f} Z")
    return f'<path d="{path}" fill="{color}"><title>{html.escape(tip)}</title></path>'


def _legend(x, y, items):
    out, cx = [], x
    for label, color in items:
        out.append(f'<rect x="{cx}" y="{y - 9}" width="10" height="10" rx="2" fill="{color}"/>')
        out.append(_text(cx + 14, y, label, 12, INK2))
        cx += 24 + 6.6 * len(label)
    return out


def fig_accuracy(rows: list[dict], set_name: str) -> str:
    sel = [r for r in rows if r["set"] == set_name and r["effort"] in ("high", "—")]
    models = sorted({r["model"] for r in sel})
    conds = [c for c in CONDITIONS if any(r["condition"] == c for r in sel)]
    W, H, L, R, T, B = max(520, 150 * len(models) + 140), 380, 56, 16, 56, 70
    pw, ph = W - L - R, H - T - B
    y = lambda v: T + ph * (1 - v)
    body = [_text(L, 22, f"Accuracy on {set_name}, by model and condition", 15, INK, weight="600"),
            _text(L, 40, "Share of tasks fully correct · bars show 95% Wilson intervals", 12, MUTED)]
    for v in (0, .25, .5, .75, 1):
        body.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}" stroke-width="1"/>')
        body.append(_text(L - 8, y(v) + 4, f"{v:.0%}", 11, MUTED, "end"))
    gw = pw / max(1, len(models))
    bw = min(34, (gw - 24) / max(1, len(conds)) - 2)
    for gi, m in enumerate(models):
        gx = L + gi * gw + (gw - (bw + 2) * len(conds)) / 2
        for ci, c in enumerate(conds):
            r = next((r for r in sel if r["model"] == m and r["condition"] == c), None)
            if not r:
                continue
            x = gx + ci * (bw + 2)
            tip = (f"{m} · {LABEL[c]}: {r['accuracy']:.1%} ({r['correct']}/{r['runs']}), 95% CI "
                   f"{r['ci_lo']:.1%}–{r['ci_hi']:.1%}")
            body.append(_bar(x, y(0), y(r["accuracy"]), bw, COLOR[c], tip))
            cx = x + bw / 2
            body.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(r["ci_lo"]):.1f}" y2="{y(r["ci_hi"]):.1f}" '
                        f'stroke="{INK}" stroke-width="1.5"/>')
            for v in (r["ci_lo"], r["ci_hi"]):
                body.append(f'<line x1="{cx - 4:.1f}" x2="{cx + 4:.1f}" y1="{y(v):.1f}" y2="{y(v):.1f}" '
                            f'stroke="{INK}" stroke-width="1.5"/>')
            body.append(_text(cx, y(r["ci_hi"]) - 5, f"{r['accuracy'] * 100:.0f}", 10, INK2, "middle"))
        body.append(_text(L + gi * gw + gw / 2, H - B + 18, m, 12, INK, "middle"))
    body.append(f'<line x1="{L}" x2="{W - R}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="{INK2}" stroke-width="1"/>')
    body += _legend(L, H - 18, [(LABEL[c], COLOR[c]) for c in conds])
    return _svg(W, H, body, f"Accuracy on {set_name}", "Grouped bars: accuracy per model and condition with 95% CIs.")


def size_bins(runs: list[dict]) -> list[tuple[int, int]]:
    edges = [0, 2_000, 4_000, 8_000, 16_000, 10 ** 9]
    return list(zip(edges, edges[1:]))


def fig_size(runs: list[dict]) -> str:
    bins = size_bins(runs)
    labels = ["<2k", "2–4k", "4–8k", "8–16k", "≥16k"]
    models = sorted({r["model"] for r in runs if r["cond"] in ("base", "harness") and r["effort"] in ("high", "—")})
    pw_one, ph = 230, 200
    L, T, gap = 56, 96, 40
    W = L + len(models) * (pw_one + gap) + 10
    H = T + ph + 80
    body = [_text(L, 22, "Accuracy vs task size", 15, INK, weight="600"),
            _text(L, 40, "Prompt length in characters, pooled over task sets · points with fewer than 3 runs omitted",
                  12, MUTED)]
    for mi, m in enumerate(models):
        x0 = L + mi * (pw_one + gap)
        xs = lambda k: x0 + 14 + k * (pw_one - 28) / (len(bins) - 1)
        y = lambda v: T + ph * (1 - v)
        for v in (0, .5, 1):
            body.append(f'<line x1="{x0}" x2="{x0 + pw_one}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}"/>')
            if mi == 0:
                body.append(_text(x0 - 8, y(v) + 4, f"{v:.0%}", 11, MUTED, "end"))
        for k, lab in enumerate(labels):
            body.append(_text(xs(k), T + ph + 16, lab, 10, MUTED, "middle"))
        body.append(_text(x0 + pw_one / 2, T - 30, m, 12, INK, "middle", "600"))
        for c in ("base", "harness"):
            pts = []
            for r in runs:
                if r["model"] != m or r["cond"] != c or r["effort"] not in ("high", "—"):
                    continue
                for x in r["rows"]:
                    n = len(r["tasks"][x["task_id"]].prompt)
                    k = next(i for i, (a, b) in enumerate(bins) if a <= n < b)
                    pts.append((k, x["grade"]["correct"]))
            series = []
            for k in range(len(bins)):
                v = [ok for kk, ok in pts if kk == k]
                if len(v) >= 3:
                    series.append((k, sum(v) / len(v), len(v)))
            if len(series) > 1:
                d = " ".join(f"{'M' if j == 0 else 'L'}{xs(k):.1f},{y(a):.1f}" for j, (k, a, _) in enumerate(series))
                body.append(f'<path d="{d}" fill="none" stroke="{COLOR[c]}" stroke-width="2"/>')
            for k, a, n in series:
                tip = html.escape(f"{m} · {LABEL[c]} · {labels[k]} chars: {a:.1%} of {n} runs")
                body.append(f'<circle cx="{xs(k):.1f}" cy="{y(a):.1f}" r="4.5" fill="{COLOR[c]}" stroke="{SURFACE}" '
                            f'stroke-width="2"><title>{tip}</title></circle>')
            if series:
                k, a, _ = series[-1]
                body.append(_text(xs(k), y(a) + (-10 if c == "harness" else 18), "Harness" if c == "harness" else "No harness",
                                  10, INK2, "middle"))
    body += _legend(L, H - 14, [(LABEL["base"], COLOR["base"]), (LABEL["harness"], COLOR["harness"])])
    return _svg(W, H, body, "Accuracy vs task size", "Small multiples per model: accuracy by prompt-length bin.")


def fig_failures(ft: list[dict]) -> str:
    rows = [r for r in ft if r["effort"] in ("high", "—")]
    rows.sort(key=lambda r: (r["set"], r["model"], CONDITIONS.index(r["condition"])))
    cats = [c for c in FAILURE_ORDER if any(r[c] for r in rows)]
    L, T, rowh = 430, 70, 22
    W, H = 900, T + rowh * len(rows) + 90
    pw = W - L - 60
    top = max([sum(r[c] for c in cats) / r["runs"] for r in rows] + [0.01])
    scale = next(v for v in (0.05, 0.1, 0.2, 0.25, 0.5, 1.0) if v >= top)
    body = [_text(16, 22, "Why runs failed", 15, INK, weight="600"),
            _text(16, 40, f"Share of each run's tasks that failed, by category (axis to {scale:.0%})", 12, MUTED)]
    for k in range(5):
        gx = L + pw * k / 4
        body.append(f'<line x1="{gx:.1f}" x2="{gx:.1f}" y1="{T - 4}" y2="{T + rowh * len(rows)}" stroke="{GRID}"/>')
        body.append(_text(gx, T + rowh * len(rows) + 16, f"{scale * k / 4:.1%}", 10, MUTED, "middle"))
    for i, r in enumerate(rows):
        y0 = T + i * rowh
        body.append(_text(L - 8, y0 + 14, f"{r['set']} · {r['model']} · {LABEL[r['condition']]}", 11, INK2, "end"))
        x = L
        for c in cats:
            if not r[c]:
                continue
            w = pw * r[c] / r["runs"] / scale
            tip = html.escape(f"{c}: {r[c]} of {r['runs']} runs")
            body.append(f'<rect x="{x:.1f}" y="{y0 + 3}" width="{max(w - 2, 1):.1f}" height="{rowh - 7}" rx="2" '
                        f'fill="{FAILURE_COLOR[c]}"><title>{tip}</title></rect>')
            x += w
        total = sum(r[c] for c in cats)
        body.append(_text(x + 6, y0 + 14, f"{total}/{r['runs']}", 10, MUTED))
    lx, ly = 16, H - 36
    for c in cats:
        body.append(f'<rect x="{lx}" y="{ly - 9}" width="10" height="10" rx="2" fill="{FAILURE_COLOR[c]}"/>')
        body.append(_text(lx + 14, ly, c, 11, INK2))
        lx += 26 + 6.2 * len(c)
        if lx > W - 160:
            lx, ly = 16, ly + 18
    return _svg(W, H, body, "Failure categories", "Stacked bars: failure categories per run.")


def fig_pareto(rt: list[dict]) -> str:
    pts = []
    for m in sorted({r["model"] for r in rt}):
        for c in CONDITIONS:
            sel = [r for r in rt if r["model"] == m and r["condition"] == c and r["effort"] in ("high", "—")
                   and r["cost_usd"] is not None]
            if sel:
                runs = sum(r["runs"] for r in sel)
                pts.append((m, c, sum(r["cost_usd"] for r in sel) / runs, sum(r["correct"] for r in sel) / runs, runs))
    W, H, L, R, T, B = 640, 420, 64, 40, 76, 60
    pw, ph = W - L - R, H - T - B
    if not pts:
        return _svg(W, 120, [_text(16, 40, "No runs with recorded cost yet.", 13, INK2)], "Cost vs accuracy", "")
    lo, hi = math.log10(min(p[2] for p in pts) / 1.5), math.log10(max(p[2] for p in pts) * 1.5)
    ymin = max(0.0, math.floor((min(p[3] for p in pts) - 0.05) * 20) / 20)
    x = lambda v: L + pw * (math.log10(v) - lo) / (hi - lo)
    y = lambda v: T + ph * (1 - (v - ymin) / (1 - ymin))
    body = [_text(L, 22, "Cost per task vs accuracy", 15, INK, weight="600"),
            _text(L, 40, "Pooled over task sets · log cost axis · line joins runs no other run beats on both", 12, MUTED)]
    for e in range(math.floor(lo), math.ceil(hi) + 1):
        for mult in (1, 2, 5):
            v = mult * 10 ** e
            if lo <= math.log10(v) <= hi:
                body.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{T}" y2="{T + ph}" stroke="{GRID}"/>')
                body.append(_text(x(v), T + ph + 16, f"${v:g}", 10, MUTED, "middle"))
    for k in range(5):
        v = ymin + (1 - ymin) * k / 4
        body.append(f'<line x1="{L}" x2="{L + pw}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}"/>')
        body.append(_text(L - 8, y(v) + 4, f"{v:.0%}" if abs(v * 100 - round(v * 100)) < 1e-9 else f"{v:.1%}",
                          11, MUTED, "end"))
    front = sorted(p for p in pts if not any(q[2] <= p[2] and q[3] >= p[3] and q != p for q in pts))
    front.sort(key=lambda p: p[2])
    if len(front) > 1:
        d = " ".join(f"{'M' if j == 0 else 'L'}{x(p[2]):.1f},{y(p[3]):.1f}" for j, p in enumerate(front))
        body.append(f'<path d="{d}" fill="none" stroke="{MUTED}" stroke-width="1.5" stroke-dasharray="4 3"/>')
    shapes = {"base": "circle", "harness": "circle", "code": "rect", "submit": "rect"}
    for m, c, cost, acc, n in pts:
        tip = f"{m} · {LABEL[c]}: ${cost:.4f} per task, {acc:.1%} correct ({n} runs)"
        if shapes[c] == "circle":
            body.append(f'<circle cx="{x(cost):.1f}" cy="{y(acc):.1f}" r="5.5" fill="{COLOR[c]}" stroke="{SURFACE}" '
                        f'stroke-width="2"><title>{html.escape(tip)}</title></circle>')
        else:
            body.append(f'<rect x="{x(cost) - 5:.1f}" y="{y(acc) - 5:.1f}" width="10" height="10" rx="2" fill="{COLOR[c]}" '
                        f'stroke="{SURFACE}" stroke-width="2"><title>{html.escape(tip)}</title></rect>')
        dy = {"base": -10, "harness": 17, "code": -10, "submit": 17}[c]
        body.append(_text(x(cost), y(acc) + dy, m.replace("claude-", ""), 10, INK2, "middle"))
    body += _legend(L, H - 12, [(LABEL[c], COLOR[c]) for c in CONDITIONS if any(p[1] == c for p in pts)])
    return _svg(W, H, body, "Cost vs accuracy", "Scatter of cost per task against accuracy with the frontier.")


# ---------------------------------------------------------------- the command

def _fmt(v, kind="pct"):
    if v is None:
        return "—"
    return {"pct": f"{v:.1%}", "usd": f"${v:.4f}", "pts": f"{v * 100:+.1f}", "p": f"{v:.3g}", "int": f"{v:.0f}",
            "f1": f"{v:.1f}"}[kind]


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def build(results_dirs: list[Path], data_dir: Path, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    runs = load(results_dirs, data_dir)
    rt, pt, ft = run_table(runs), paired_table(runs), failure_table(runs)
    write_csv(out / "runs.csv", rt); write_csv(out / "paired.csv", pt); write_csv(out / "failures.csv", ft)
    figs = []
    for s in sorted({r["set"] for r in rt}):
        (out / f"fig_accuracy_{s}.svg").write_text(fig_accuracy(rt, s)); figs.append(f"fig_accuracy_{s}.svg")
    for name, svg in (("fig_size.svg", fig_size(runs)), ("fig_failures.svg", fig_failures(ft)),
                      ("fig_pareto.svg", fig_pareto(rt))):
        (out / name).write_text(svg); figs.append(name)
    md = ["# ConstructBench results", "", f"{len(runs)} run files across {len({r['set'] for r in rt})} task sets.", "",
          "## Runs", "", "| Set | Model | Condition | Effort | Tasks | Runs | Accuracy (95% CI) | Field | Cost | $/correct | "
          "Out tok | s/run |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rt, key=lambda r: (r["set"], r["model"], CONDITIONS.index(r["condition"]), r["effort"])):
        md.append(f"| {r['set']} | {r['model']} | {LABEL[r['condition']]} | {r['effort']} | {r['tasks']} | {r['runs']} | "
                  f"{_fmt(r['accuracy'])} ({_fmt(r['ci_lo'])}–{_fmt(r['ci_hi'])}) | {_fmt(r['field_score'])} | "
                  f"{_fmt(r['cost_usd'], 'usd')} | {_fmt(r['cost_per_correct'], 'usd')} | "
                  f"{_fmt(r['mean_output_tokens'], 'int')} | {_fmt(r['mean_seconds'], 'f1')} |")
    md += ["", "## Each condition vs the same model's baseline (paired by task)", "",
           "| Set | Model | Effort | Condition | Tasks | Δ accuracy, pts (95% CI) | Better / worse tasks | p (sign-flip) | "
           "p (McNemar) | $/correct vs base |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in pt:
        md.append(f"| {r['set']} | {r['model']} | {r['effort']} | {LABEL[r['condition']]} | {r['tasks']} | "
                  f"{_fmt(r['diff'], 'pts')} ({_fmt(r['diff_ci_lo'], 'pts')} to {_fmt(r['diff_ci_hi'], 'pts')}) | "
                  f"{r['condition_better']} / {r['base_better']} | {_fmt(r['p_sign_flip'], 'p')} | "
                  f"{_fmt(r['p_mcnemar'], 'p')} | {_fmt(r['cost_per_correct_condition'], 'usd')} vs "
                  f"{_fmt(r['cost_per_correct_base'], 'usd')} |")
    cats = [c for c in FAILURE_ORDER if any(r[c] for r in ft)]
    md += ["", "## Failure categories (runs)", "", "| Set | Model | Condition | Effort | Runs | " + " | ".join(cats) + " |",
           "|---|---|---|---|---|" + "---|" * len(cats)]
    for r in ft:
        md.append(f"| {r['set']} | {r['model']} | {LABEL[r['condition']]} | {r['effort']} | {r['runs']} | "
                  + " | ".join(str(r[c]) for c in cats) + " |")
    md += ["", "## Figures", ""] + [f"![{f}]({f})" for f in figs]
    md += ["", "Costs are client-side estimates from token usage × list price (Claude); runs without a recorded cost "
               "are left out of cost columns and the Pareto figure. Accuracy CIs are Wilson intervals over runs; paired "
               "differences use the task as the unit (repeats averaged) with a bootstrap CI."]
    (out / "report.md").write_text("\n".join(md) + "\n")
    return out / "report.md"
