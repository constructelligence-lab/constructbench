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
from .generators import finance, field_ops, documents, design, precon, visual, scheduling, safety, robotics, built_world, quality_contracts, bim, expert, extreme

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
    # scheduling
    "critical_path": scheduling.critical_path,
    "float": scheduling.floats,
    "delay_impact": scheduling.delay_impact,
    "lookahead": scheduling.lookahead,
    "schedule_health": scheduling.health,
    # project management
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
    # safety (the last three are rendered drawings)
    "incident_rates": safety.incident_rates,
    "fall_clearance": safety.fall_clearance,
    "excavation": safety.trench,
    "ladder_image": safety.ladder,
    "crane_zone_image": safety.crane_zone,
    "guardrail_image": safety.guardrail,
    # construction robotics (path_planning is a rendered occupancy map)
    "path_planning": robotics.path_planning,
    "layout_transform": robotics.layout_transform,
    "kinematics": robotics.arm,
    "drone_survey": robotics.drone_survey,
    "rebar_tying": robotics.rebar_tying,
    "bricklaying": robotics.bricklaying,
    # civil & infrastructure
    "earthwork": built_world.earthwork,
    "gravity_pipe": built_world.gravity_pipe,
    "paving": built_world.paving,
    "leveling": quality_contracts.leveling,
    # sustainability & energy
    "embodied_carbon": built_world.embodied_carbon,
    "energy_use": built_world.eui,
    "solar_pv": built_world.solar,
    # real estate & facilities
    "pro_forma": built_world.pro_forma,
    "lifecycle_cost": built_world.lifecycle,
    "maintenance_priority": built_world.maintenance,
    # quality control
    "concrete_acceptance": quality_contracts.concrete_acceptance,
    "compaction": quality_contracts.compaction,
    # contracts & claims
    "delay_claim": quality_contracts.delay_claim,
    "notice_deadlines": quality_contracts.notice_deadlines,
    # BIM & digital construction
    "clash_detection": bim.clash_detection,
    "ifc_quantities": bim.ifc_quantities,
    "asset_register": bim.asset_register,
    "file_naming": bim.file_naming,
    "model_5d": bim.model_5d,
    # expert tier (difficulty "expert"): volume + interacting conventions + real-document traps
    "pdm_calendar": expert.pdm_calendar,
    "pay_app_certification": expert.pay_app_certification,
    "wip_portfolio": expert.wip_portfolio,
    "cost_ledger": expert.cost_ledger,
    "mass_haul": expert.mass_haul,
    "delay_tia": expert.delay_tia,
    "bid_leveling_expert": expert.bid_leveling_expert,
    # extreme tier: several documents / rule layers interacting at size
    "co_reconciliation": extreme.co_reconciliation,
    "addendum_takeoff": extreme.addendum_takeoff,
    "ledger_xl": extreme.ledger_xl,
    "cashflow_forecast": extreme.cashflow_forecast,
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
