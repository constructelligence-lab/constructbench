"""Running a provider over a task set, resumably, and scoring the results.

Results are JSONL, one line per task, holding the raw response so a run can be re-graded after a grader fix
without paying for it again. Re-running the same output file skips tasks already answered.
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def run(provider: Provider, tasks: list[Task], out: Path, workers: int = 4, log=print) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for l in out.read_text().splitlines():
            if l.strip():
                done.add(json.loads(l)["task_id"])
    todo = [t for t in tasks if t.id not in done]
    skipped = [t for t in todo if t.attachments and not provider.supports_images]
    todo = [t for t in todo if not (t.attachments and not provider.supports_images)]
    if skipped:
        log(f"{len(skipped)} image tasks skipped: {provider.name} takes text only")
    log(f"{provider.name}: {len(todo)} to run, {len(done)} already done")
    with out.open("a") as f, ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(provider.answer, t): t for t in todo}
        for n, fut in enumerate(as_completed(futures), 1):
            t = futures[fut]
            r = fut.result()
            g = grade(t, r.text)
            f.write(json.dumps({"task_id": t.id, "domain": t.domain, "category": t.category, "provider": provider.name,
                                "response": asdict(r), "grade": asdict(g)}) + "\n")
            f.flush()
            log(f"  [{n}/{len(todo)}] {t.id}: {'correct' if g.correct else 'wrong' if g.parsed else 'no answer'}")
    return out


def regrade(results: Path, tasks: list[Task]) -> list[dict]:
    """Grade stored responses again with the current grader and task set."""
    by_id = {t.id: t for t in tasks}
    rows = []
    for l in results.read_text().splitlines():
        if not l.strip():
            continue
        row = json.loads(l)
        t = by_id.get(row["task_id"])
        if t is None:
            continue
        row["grade"] = asdict(grade(t, row["response"]["text"]))
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
        return {"n": n, "correct": k, "accuracy": k / n if n else 0.0, "ci95": [lo, hi], "field_score": partial,
                "unparsed": sum(1 for r in sel if not r["grade"]["parsed"]),
                "errors": sum(1 for r in sel if not r["response"]["ok"])}
    out = {"overall": agg(rows), "domains": {}, "categories": {}}
    for d in DOMAINS:
        sel = [r for r in rows if r["domain"] == d]
        if sel:
            out["domains"][d] = agg(sel)
    for c in sorted({r["category"] for r in rows}):
        out["categories"][c] = agg([r for r in rows if r["category"] == c])
    toks = [r["response"].get("output_tokens") for r in rows if r["response"].get("output_tokens")]
    out["mean_output_tokens"] = sum(toks) / len(toks) if toks else None
    return out
