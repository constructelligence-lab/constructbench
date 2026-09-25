"""Every task family, and building a task set from a seed.

A set is fully determined by (seed, per-family count): the same seed rebuilds the same prompts, images and
answers byte for byte. Publish results on a public dev seed; keep a private seed for held-out scoring so a
model can't be tuned to the exact items.
"""
from __future__ import annotations

import hashlib
import random
from typing import Callable

from .task import Task, DOMAINS
from .generators import finance, field_ops, documents, design, precon, visual

Family = Callable[[random.Random, int], Task]

FAMILIES: dict[str, Family] = {
    # architecture
    "occupancy_egress": design.occupancy,
    "stairs": design.stairs,
    "zoning": design.zoning,
    # design & engineering
    "structural": design.beam,
    "electrical": design.electrical,
    "mechanical": design.duct,
    # estimating
    "quantities": field_ops.quantities,
    "unit_rate": precon.unit_estimate,
    "change_orders": finance.change_order,
    # preconstruction
    "bid_leveling": precon.bid_leveling,
    "bid_day": precon.bid_day,
    # project management
    "scheduling": field_ops.cpm,
    "evm": finance.evm,
    "labor": field_ops.labor,
    "rfi_log": precon.rfi_log,
    # finance
    "wip": finance.wip,
    "retainage": finance.retainage,
    "cash_flow": field_ops.cash,
    # document recognition
    "extraction": documents.extraction,
    "pay_applications": field_ops.g703,
    # visual intelligence
    "floor_plan": visual.floor_plan,
    "symbol_count": visual.symbols,
    "gantt": visual.gantt,
}


def _family_rng(seed: int, family: str, i: int) -> random.Random:
    # Independent stream per (seed, family, item): adding a family or changing one generator never
    # shifts the items of another.
    h = hashlib.sha256(f"{seed}:{family}:{i}".encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def build(seed: int = 1, per_family: int = 5, domains: list[str] | None = None, families: list[str] | None = None) -> list[Task]:
    tasks: list[Task] = []
    for name, fn in FAMILIES.items():
        if families and name not in families:
            continue
        for i in range(per_family):
            t = fn(_family_rng(seed, name, i), i)
            if domains and t.domain not in domains:
                break
            assert t.domain in DOMAINS, f"{name} produced unknown domain {t.domain}"
            t.meta = {**t.meta, "family": name, "seed": seed}
            tasks.append(t)
    return tasks
