"""Is a training corpus contaminated with benchmark items?

Prompts from one family share their wording on purpose (the template states the rule), so template overlap is
expected and harmless. What contaminates a score is an *item*: the same numbers in the same order. Two signals,
either of which flags a task:

* **n-grams with numbers** — a long n-gram of the normalised prompt that holds at least ``min_numbers`` numbers
  appears in the corpus (template sentences, which have no numbers, never flag);
* **number fingerprint** — a run of ``run`` consecutive numbers from the prompt (all of them, if the prompt has
  fewer) appears consecutively among a corpus string's numbers. This catches short, number-sparse prompts (a
  stair with three dimensions) that no long n-gram covers.

A task is contaminated when the corpus holds at least ``coverage`` (default half) of its fingerprint units, and
either two or more of them or the item's whole number sequence in order: a leaked item matches nearly all of
them, a coincidence (two items that drew the same few option values) one. An n-gram or run that two benchmark items share is template (a code limit, a fixed rate table) and is ignored,
so check a whole task set at once rather than one task.

    python -m constructbench decontam data/dev.jsonl ../buildops-source/ml/general-model/data/*.jsonl
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from .task import Task

# A word that starts with a letter keeps its digits (co2e, m2, tp3) so units never read as bare numbers.
_TOKEN = re.compile(r"[a-z][a-z0-9]*|\d[\d,]*(?:\.\d+)?")
_NUMBER = re.compile(r"\d")


def tokens(text: str) -> list[str]:
    return [t.replace(",", "") for t in _TOKEN.findall(text.lower())]


def grams(toks: list[str], n: int, min_numbers: int) -> set[tuple[str, ...]]:
    out = set()
    for k in range(len(toks) - n + 1):
        g = tuple(toks[k:k + n])
        if sum(1 for t in g if _NUMBER.match(t)) >= min_numbers:
            out.add(g)
    return out


def numbers(toks: list[str]) -> list[str]:
    return [t for t in toks if _NUMBER.match(t)]


def runs(nums: list[str], size: int) -> set[tuple[str, ...]]:
    size = min(size, len(nums))
    # A run of one repeated value ("2 2 2 2") is formatting, not an item.
    return {r for k in range(len(nums) - size + 1) if len(set(r := tuple(nums[k:k + size]))) >= 2} if size >= 2 else set()


def corpus_texts(paths: Iterable[Path]) -> Iterable[str]:
    """Every string anywhere in each JSONL row (messages, prompts, answers) — the format does not matter."""
    def strings(v):
        if isinstance(v, str):
            yield v
        elif isinstance(v, dict):
            for x in v.values():
                yield from strings(x)
        elif isinstance(v, list):
            for x in v:
                yield from strings(x)
    for path in paths:
        with Path(path).open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield from strings(json.loads(line))
                except json.JSONDecodeError:
                    yield line


def check(tasks: list[Task], corpus: Iterable[Path], n: int = 12, min_numbers: int = 3, run: int = 4,
          coverage: float = 0.5) -> dict:
    """Flag a task when the corpus holds at least ``coverage`` of its fingerprint units (n-grams + number runs)."""
    owner: dict[tuple, set[str]] = {}
    full: dict[str, str] = {}
    for t in tasks:
        toks = tokens(t.prompt)
        full[t.id] = " " + " ".join(numbers(toks)) + " "
        for g in grams(toks, n, min_numbers):
            owner.setdefault(("g",) + g, set()).add(t.id)
        for r in runs(numbers(toks), run):
            owner.setdefault(("r", len(r)) + r, set()).add(t.id)
    # Anything two different benchmark items share is template (a code limit, a fixed rate table), not an item.
    units = {u: next(iter(ids)) for u, ids in owner.items() if len(ids) == 1}
    total: dict[str, int] = {}
    for task_id in units.values():
        total[task_id] = total.get(task_id, 0) + 1
    sizes = sorted({u[1] for u in units if u[0] == "r"})
    matched: dict[str, set] = {}
    whole: set[str] = set()                       # tasks whose entire number sequence appears in order
    scanned = 0
    for text in corpus_texts(corpus):
        scanned += 1
        toks = tokens(text)
        found = {("g",) + g for g in grams(toks, n, min_numbers)}
        nums = numbers(toks)
        for size in sizes:
            found.update(("r", size) + r for r in runs(nums, size) if len(r) == size)
        hit = {units[u] for u in found if u in units}
        for u in found:
            if u in units:
                matched.setdefault(units[u], set()).add(u)
        if hit:
            joined = " " + " ".join(nums) + " "
            whole.update(task_id for task_id in hit if task_id not in whole and full[task_id] in joined)
    share = {task_id: len(us) / total[task_id] for task_id, us in matched.items()}
    # One shared unit is a coincidence unless the item's whole number sequence is there too.
    hits = {task_id for task_id, x in share.items() if x >= coverage and (len(matched[task_id]) >= 2 or task_id in whole)}
    by_domain: dict[str, list[int]] = {}
    for t in tasks:
        by_domain.setdefault(t.domain, [0, 0])
        by_domain[t.domain][1] += 1
        by_domain[t.domain][0] += t.id in hits
    return {"tasks": len(tasks), "corpus_strings": scanned, "n": n, "min_numbers": min_numbers, "run": run, "coverage": coverage,
            "contaminated": len(hits), "contaminated_rate": round(len(hits) / max(1, len(tasks)), 4),
            "partial_overlap": len(share) - len(hits),
            "by_domain": {d: {"contaminated": c, "tasks": total_} for d, (c, total_) in sorted(by_domain.items())},
            "task_ids": sorted(hits)}
