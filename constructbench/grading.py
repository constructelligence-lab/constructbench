"""Extracting a model's answer and grading it field by field.

The contract with the model is one line: `ANSWER: {json}`. Working before it is allowed and ignored.
Parsing is forgiving about wrapping (code fences, a trailing period, `$`/`,` inside numeric strings)
and strict about substance: a missing key is wrong, a number outside tolerance is wrong.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from .task import FieldSpec, Task

_ANSWER_RE = re.compile(r"ANSWER\s*:\s*(\{.*\})", re.S | re.I)
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def extract_answer(text: str, lenient: bool = False) -> dict[str, Any] | None:
    """The JSON object after the last `ANSWER:` in the response, or None.

    With `lenient=True` a response that never wrote the `ANSWER:` line is still read: the first fenced JSON object,
    else the first balanced `{...}`. That exists to REPORT format compliance separately, never to replace the strict
    score — a benchmark that scores a correct value as zero because of its serialisation is measuring formatting.
    """
    if not text:
        return None
    # Last occurrence wins: models sometimes restate the format before answering.
    idx = [m.start() for m in re.finditer(r"ANSWER\s*:", text, re.I)]
    for start in reversed(idx):
        chunk = text[start:]
        m = _ANSWER_RE.match(chunk)
        if not m:
            continue
        body = _balanced_object(m.group(1))
        if body is None:
            continue
        try:
            value = json.loads(body)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return _lenient_object(text) if lenient else None


def _lenient_object(text: str) -> dict[str, Any] | None:
    """An answer the model printed as JSON without the ANSWER line: a fenced block first, then any balanced object."""
    for m in _FENCE_RE.finditer(text):
        try:
            value = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value:
            return value
    start = text.find("{")
    while start != -1:
        body = _balanced_object(text[start:])
        if body:
            try:
                value = json.loads(body)
            except json.JSONDecodeError:
                value = None
            if isinstance(value, dict) and value:
                return value
        start = text.find("{", start + 1)
    return None


def _balanced_object(s: str) -> str | None:
    """The first balanced {...} in s, respecting strings."""
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[: i + 1]
    return None


def _to_number(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    if isinstance(v, str):
        s = v.strip().replace(",", "").replace("$", "").replace("%", "").strip()
        neg = s.startswith("(") and s.endswith(")")
        s = s.strip("()")
        try:
            x = float(s)
        except ValueError:
            return None
        return -x if neg else x
    return None


def _norm_text(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v)).strip().casefold()


def grade_field(spec: FieldSpec, expected: Any, got: Any) -> bool:
    if got is None:
        return False
    k = spec.kind
    if k == "number":
        g, e = _to_number(got), float(expected)
        if g is None:
            return False
        tol = max(abs(e) * spec.rel_tol, spec.abs_tol)
        return abs(g - e) <= tol + 1e-9
    if k == "integer":
        g = _to_number(got)
        return g is not None and float(g).is_integer() and int(g) == int(expected)
    if k in ("text", "date"):
        return _norm_text(got) == _norm_text(expected)
    if k in ("set", "list"):
        if not isinstance(got, list):
            return False
        g = [_norm_text(x) for x in got]
        e = [_norm_text(x) for x in expected]
        return sorted(g) == sorted(e) if k == "set" else g == e
    raise ValueError(f"unknown field kind {k}")


@dataclass
class Grade:
    task_id: str
    category: str
    parsed: bool
    correct: bool                 # every field right
    field_score: float            # share of fields right (partial credit)
    fields: dict[str, bool]


def grade(task: Task, response_text: str, lenient: bool = False) -> Grade:
    ans = extract_answer(response_text, lenient=lenient)
    if ans is None:
        return Grade(task.id, task.category, False, False, 0.0, {k: False for k in task.fields})
    lowered = {str(k).strip().lower(): v for k, v in ans.items()}
    per = {k: grade_field(spec, task.answer[k], lowered.get(k.lower())) for k, spec in task.fields.items()}
    score = sum(per.values()) / len(per)
    return Grade(task.id, task.category, True, all(per.values()), score, per)
