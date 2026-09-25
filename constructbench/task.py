"""A benchmark task: a prompt, the reference answer, and how to grade each field of it.

Every answer is computed by the generator's reference implementation from the same parameters the
prompt states — nothing is hand-keyed, so a wrong reference is a bug in code, which the tests catch.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class FieldSpec:
    """How one answer field is graded.

    kind:
      number  — within rel_tol of the reference, or abs_tol, whichever is looser
      integer — exact integer
      text    — case- and whitespace-insensitive exact match
      date    — ISO date (YYYY-MM-DD) exact
      set     — same members, order ignored (members compared as text)
      list    — same members in the same order (members compared as text)
    """
    kind: str
    rel_tol: float = 0.0
    abs_tol: float = 0.0


def number(rel_tol: float = 0.005, abs_tol: float = 0.0) -> FieldSpec:
    return FieldSpec("number", rel_tol=rel_tol, abs_tol=abs_tol)


INTEGER = FieldSpec("integer")
TEXT = FieldSpec("text")
DATE = FieldSpec("date")
SET = FieldSpec("set")
LIST = FieldSpec("list")


# The parts of construction work the benchmark measures. Each task belongs to one.
DOMAINS = {
    "architecture": "Architecture — code-driven design checks: occupancy, egress, stairs, zoning",
    "design": "Design & engineering — structural, electrical and mechanical sizing",
    "estimating": "Estimating — quantity takeoff, unit-rate estimates, change-order pricing",
    "preconstruction": "Preconstruction — bid leveling, scope gaps, the bid-day number",
    "scheduling": "Scheduling — critical path, float, delay impact, look-aheads, schedule quality",
    "project_management": "Project management — earned value, productivity, RFIs",
    "finance": "Cost control & finance — WIP, retainage, cash flow",
    "document_recognition": "Document recognition — reading invoices, tickets, waivers and pay applications",
    "visual_intelligence": "Visual intelligence — reading drawings and charts from images",
    "safety": "Safety — incident rates, fall clearance, excavation, and hazards read from rendered drawings",
    "robotics": "Construction robotics — navigation on occupancy maps, layout transforms, arm kinematics, drone survey plans, robot vs crew productivity",
    "civil": "Civil & infrastructure — earthwork, gravity drainage, paving",
    "sustainability": "Sustainability & energy — embodied carbon, energy use intensity, solar PV",
    "real_estate": "Real estate & facilities — development pro formas, lifecycle cost, maintenance priority",
}


@dataclass
class Task:
    id: str
    domain: str
    category: str
    title: str
    difficulty: str                      # easy | medium | hard
    prompt: str
    answer: dict[str, Any]
    fields: dict[str, FieldSpec]
    meta: dict[str, Any] = field(default_factory=dict)
    # Images the prompt refers to: [{"media_type": "image/png", "data": <base64>, "name": ...}].
    attachments: list[dict[str, str]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["fields"] = {k: asdict(v) for k, v in self.fields.items()}
        return d

    @staticmethod
    def from_json(d: dict[str, Any]) -> "Task":
        return Task(
            id=d["id"], domain=d["domain"], category=d["category"], title=d["title"], difficulty=d["difficulty"],
            prompt=d["prompt"], answer=d["answer"],
            fields={k: FieldSpec(**v) for k, v in d["fields"].items()}, meta=d.get("meta", {}),
            attachments=d.get("attachments", []),
        )


def answer_keys_line(fields: dict[str, FieldSpec]) -> str:
    """The instruction every prompt ends with, naming the exact keys and their types."""
    kinds = {"number": "number", "integer": "integer", "text": "string", "date": "string YYYY-MM-DD",
             "set": "array", "list": "array (in order)"}
    parts = [f'"{k}" ({kinds[v.kind]})' for k, v in fields.items()]
    return "Answer keys: " + ", ".join(parts) + "."
