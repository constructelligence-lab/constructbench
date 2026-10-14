"""Running a provider over a task set, resumably, and scoring the results.

Results are JSONL, one line per task, holding the raw response so a run can be re-graded after a grader fix
without paying for it again. Re-running the same output file skips tasks already answered.
"""
from __future__ import annotations

import json
import math
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .grading import grade
from .providers import Provider
from .task import Task, DOMAINS


def load_tasks(path: Path) -> list[Task]:
    return [Task.from_json(json.loads(l)) for l in path.read_text().splitlines() if l.strip()]


def save_tasks(tasks: Iterable[Task], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(t.to_json()) + "\n" for t in tasks))


def spent(files: Iterable[Path]) -> float:
    """Dollars already recorded (response.extra.cost_usd) across result files — what a budget counts against."""
    total = 0.0
    for p in files:
        if p.exists():
            for l in p.read_text().splitlines():
                if l.strip():
                    total += ((json.loads(l).get("response") or {}).get("extra") or {}).get("cost_usd") or 0.0
    return total


def run(provider: Provider, tasks: list[Task], out: Path, workers: int = 4, log=print,
        budget: float | None = None, budget_files: Iterable[Path] = ()) -> Path:
    """`budget` (USD) is a hard stop: a task starts only if what is spent so far (in `budget_files` + `out`), plus
    the running mean cost per task for every task in flight, stays under it. Providers that report no cost_usd
    count as free."""
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for l in out.read_text().splitlines():
            if l.strip():
                row = json.loads(l)
                resp = row.get("response") or {}
                # an API failure (rate limit, outage) is not an answer: run it again; a refusal is the model's answer
                if resp.get("ok", True) or resp.get("error") == "refusal":
                    done.add(row["task_id"])
                else:
                    done.discard(row["task_id"])
    todo = [t for t in tasks if t.id not in done]
    skipped = [t for t in todo if t.attachments and not provider.supports_images]
    todo = [t for t in todo if not (t.attachments and not provider.supports_images)]
    if skipped:
        log(f"{len(skipped)} image tasks skipped: {provider.name} takes text only")
    log(f"{provider.name}: {len(todo)} to run, {len(done)} already done")
    files = {Path(p).resolve() for p in budget_files} | {out.resolve()}
    so_far = spent(files) if budget is not None else 0.0
    costs: list[float] = []
    queue, inflight, n = list(todo), {}, 0

    def affordable() -> bool:
        if budget is None:
            return True
        if not costs:                       # no price seen yet: one task at a time until there is one
            return not inflight and so_far < budget
        mean = sum(costs) / len(costs)
        return so_far + mean * (len(inflight) + 1) < budget

    with out.open("a") as f, ThreadPoolExecutor(max_workers=workers) as pool:
        while queue or inflight:
            while queue and len(inflight) < workers and affordable():
                t = queue.pop(0)
                inflight[pool.submit(provider.answer, t)] = t
            if not inflight:
                log(f"budget ${budget:.2f} reached (${so_far:.2f} spent): {len(queue)} tasks not run — re-run to resume")
                break
            finished, _ = wait(inflight, return_when=FIRST_COMPLETED)
            for fut in finished:
                t = inflight.pop(fut)
                r = fut.result()
                g = grade(t, r.text)
                cost = (r.extra or {}).get("cost_usd")
                if cost is not None:
                    so_far += cost
                    costs.append(cost)
                n += 1
                f.write(json.dumps({"task_id": t.id, "domain": t.domain, "category": t.category,
                                    "difficulty": t.difficulty, "provider": provider.name,
                                    "response": asdict(r), "grade": asdict(g)}) + "\n")
                f.flush()
                money = f"  ${cost:.3f} (total ${so_far:.2f})" if cost is not None else ""
                log(f"  [{n}/{len(todo)}] {t.id}: {'correct' if g.correct else 'wrong' if g.parsed else 'no answer'}"
                    + (f" — {r.error}" if r.error else "") + money)
    return out


def regrade(results: Path, tasks: list[Task]) -> list[dict]:
    """Grade stored responses again with the current grader and task set."""
    by_id = {t.id: t for t in tasks}
    latest: dict[str, dict] = {}
    for l in results.read_text().splitlines():
        if l.strip():
            row = json.loads(l)
            latest[row["task_id"]] = row          # a re-run of a failed call supersedes it
    rows = []
    for row in latest.values():
        t = by_id.get(row["task_id"])
        if t is None:
            continue
        row["grade"] = asdict(grade(t, row["response"]["text"]))
        row["difficulty"] = t.difficulty          # older result files predate this field
        rows.append(row)
    return rows


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for a proportion — honest error bars for small task counts."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def summarize(rows: list[dict]) -> dict:
    def agg(sel):
        n = len(sel)
        k = sum(1 for r in sel if r["grade"]["correct"])
        partial = sum(r["grade"]["field_score"] for r in sel) / n if n else 0.0
        lo, hi = wilson(k, n)
        secs = [r["response"].get("seconds") or 0 for r in sel]
        toks = [r["response"].get("output_tokens") for r in sel if r["response"].get("output_tokens")]
        return {"n": n, "correct": k, "accuracy": k / n if n else 0.0, "ci95": [lo, hi], "field_score": partial,
                "unparsed": sum(1 for r in sel if not r["grade"]["parsed"]),
                "errors": sum(1 for r in sel if not r["response"]["ok"]),
                "mean_seconds": sum(secs) / n if n else 0.0,
                "mean_output_tokens": sum(toks) / len(toks) if toks else None}
    out = {"overall": agg(rows), "domains": {}, "categories": {}}
    for d in DOMAINS:
        sel = [r for r in rows if r["domain"] == d]
        if sel:
            out["domains"][d] = agg(sel)
    out["difficulty"] = {d: agg([r for r in rows if r.get("difficulty") == d]) for d in ("easy", "medium", "hard", "expert")
                         if any(r.get("difficulty") == d for r in rows)}
    for c in sorted({r["category"] for r in rows}):
        out["categories"][c] = agg([r for r in rows if r["category"] == c])
    toks = [r["response"].get("output_tokens") for r in rows if r["response"].get("output_tokens")]
    out["mean_output_tokens"] = sum(toks) / len(toks) if toks else None
    return out
