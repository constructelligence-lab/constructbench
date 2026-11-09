"""Paired statistics for comparing two conditions on the same tasks (stdlib only, deterministic).

The unit of analysis is the task: with repeats, a task's score is the share of its runs that were fully correct, so
repeats sharpen each task's score instead of being counted as independent tasks (they are not).
"""
from __future__ import annotations

import math
import random
from itertools import product


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts (b: only A right, c: only B right)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def sign_flip_p(diffs: list[float], n_mc: int = 20_000, seed: int = 0) -> float:
    """Two-sided paired permutation test on per-task differences: under H0 each difference's sign is arbitrary.
    Exact when there are at most 20 non-zero differences, Monte Carlo (fixed seed) otherwise."""
    d = [x for x in diffs if x != 0]
    if not d:
        return 1.0
    obs = abs(sum(d))
    if len(d) <= 20:
        hits = sum(1 for signs in product((1, -1), repeat=len(d))
                   if abs(sum(s * x for s, x in zip(signs, d))) >= obs - 1e-12)
        return hits / 2 ** len(d)
    rng = random.Random(seed)
    hits = sum(1 for _ in range(n_mc) if abs(sum(x if rng.random() < .5 else -x for x in d)) >= obs - 1e-12)
    return (hits + 1) / (n_mc + 1)


def bootstrap_ci(diffs: list[float], n_boot: int = 10_000, seed: int = 0, level: float = 0.95) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean per-task difference, resampling tasks (fixed seed)."""
    if not diffs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    lo = means[int((1 - level) / 2 * n_boot)]
    hi = means[min(n_boot - 1, int((1 + level) / 2 * n_boot))]
    return (lo, hi)


def mean_sd(xs: list[float]) -> tuple[float, float]:
    if not xs:
        return (0.0, 0.0)
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else 0.0
    return (m, sd)


def paired(rows_a: list[dict], rows_b: list[dict]) -> dict:
    """Compare two result sets task by task. Rows carry task_id, optional rep, grade.correct, response.extra.cost_usd.
    A side's calls that failed at the API are dropped from that side: a task the model was never allowed to attempt
    is not a wrong answer (the pre-registered rule), so it is reported as not run instead."""
    def not_ok(r):
        return not (r.get("response") or {}).get("ok", True)

    not_run_a = len({r["task_id"] for r in rows_a if not_ok(r)})
    not_run_b = len({r["task_id"] for r in rows_b if not_ok(r)})
    rows_a = [r for r in rows_a if not not_ok(r)]
    rows_b = [r for r in rows_b if not not_ok(r)]

    def by_task(rows):
        out: dict[str, list[dict]] = {}
        for r in rows:
            out.setdefault(r["task_id"], []).append(r)
        return out
    ta, tb = by_task(rows_a), by_task(rows_b)
    common = sorted(set(ta) & set(tb))
    score = lambda rs: sum(1 for r in rs if r["grade"]["correct"]) / len(rs)
    pa = [score(ta[t]) for t in common]
    pb = [score(tb[t]) for t in common]
    diffs = [x - y for x, y in zip(pa, pb)]
    single = all(len(ta[t]) == 1 and len(tb[t]) == 1 for t in common)
    b = sum(1 for x, y in zip(pa, pb) if x > y)
    c = sum(1 for x, y in zip(pa, pb) if x < y)

    def per_rep(tmap):
        reps: dict[int, list[bool]] = {}
        for t in common:
            for r in tmap[t]:
                reps.setdefault(r.get("rep", 0), []).append(r["grade"]["correct"])
        return [sum(v) / len(v) for v in reps.values()]

    def cost(tmap):
        cs = [((r["response"].get("extra") or {}).get("cost_usd")) for t in common for r in tmap[t]]
        cs = [x for x in cs if x is not None]
        right = sum(1 for t in common for r in tmap[t] if r["grade"]["correct"])
        total = sum(cs) if cs else None
        return total, (total / right if total is not None and right else None)

    ca, cb = cost(ta), cost(tb)
    return {
        "tasks": len(common), "runs_a": sum(len(ta[t]) for t in common), "runs_b": sum(len(tb[t]) for t in common),
        "not_run_a": not_run_a, "not_run_b": not_run_b,
        "acc_a": sum(pa) / len(pa) if pa else 0.0, "acc_b": sum(pb) / len(pb) if pb else 0.0,
        "diff": sum(diffs) / len(diffs) if diffs else 0.0, "diff_ci95": bootstrap_ci(diffs),
        "a_better_tasks": b, "b_better_tasks": c,
        "p_sign_flip": sign_flip_p(diffs), "p_mcnemar": mcnemar_exact(b, c) if single else None,
        "rep_acc_a": mean_sd(per_rep(ta)), "rep_acc_b": mean_sd(per_rep(tb)),
        "cost_a": ca[0], "cost_per_correct_a": ca[1], "cost_b": cb[0], "cost_per_correct_b": cb[1],
    }
