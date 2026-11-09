#!/usr/bin/env python3
"""Regenerates the diagrams in assets/ (light and dark SVG) from this repository's own registry and results.
Run: python3 scripts/make_graphics.py   (needs Python 3.10+, no other dependencies)"""
# ── svg kit: a small, dependency-free set of helpers for clean, Apple-style diagrams ─────────────────────────
# Light and dark themes, system font stack, soft cards, Apple system colours. Every graphic is generated, so it
# can be reproduced and, where it shows data, regenerated from that data.
from __future__ import annotations

import html
from pathlib import Path

SANS = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Inter, Helvetica, Arial, sans-serif'
MONO = 'ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace'

THEMES = {
    "light": dict(
        bg0="#fbfbfd", bg1="#f2f2f7", card="#ffffff", edge="#e5e5ea", text="#1d1d1f", sub="#6e6e73", faint="#aeaeb2",
        track="#e8e8ed", shadow=0.07, chip="#f5f5f7",
        blue="#007aff", green="#34c759", orange="#ff9500", pink="#ff2d55", purple="#af52de", teal="#30b0c7",
        indigo="#5856d6", yellow="#d4a000", red="#ff3b30", mint="#00a99d", cyan="#32ade6", brown="#a2845e",
        ink=dict(blue="#0062cc", green="#248a3d", orange="#b25000", pink="#d30f45", purple="#8944ab", teal="#00809a",
                 indigo="#4a48c0", yellow="#8a6500", red="#d70015", mint="#007a72", cyan="#0071a4", brown="#7f6a4d", faint="#6e6e73"),
    ),
    "dark": dict(
        bg0="#1c1c1e", bg1="#000000", card="#2c2c2e", edge="#3a3a3c", text="#f5f5f7", sub="#a1a1a6", faint="#636366",
        track="#3a3a3c", shadow=0.5, chip="#38383a",
        blue="#0a84ff", green="#30d158", orange="#ff9f0a", pink="#ff375f", purple="#bf5af2", teal="#40c8e0",
        indigo="#5e5ce6", yellow="#ffd60a", red="#ff453a", mint="#63e6e2", cyan="#64d2ff", brown="#ac8e68",
        ink=dict(blue="#0a84ff", green="#30d158", orange="#ff9f0a", pink="#ff375f", purple="#bf5af2", teal="#40c8e0",
                 indigo="#7d7aff", yellow="#ffd60a", red="#ff453a", mint="#63e6e2", cyan="#64d2ff", brown="#ac8e68", faint="#a1a1a6"),
    ),
}


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def wrap(text: str, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


def text_width(s: str, size: float, mono: bool = False, weight: int = 400) -> float:
    k = 0.60 if mono else (0.56 if weight < 600 else 0.585)
    return len(s) * size * k


class Canvas:
    def __init__(self, w: int, h: int, theme: str, title: str, desc: str, radius: int = 28):
        self.w, self.h, self.t, self.name = w, h, THEMES[theme], theme
        self.title, self.desc, self.radius = title, desc, radius
        self.parts: list[str] = []
        self.defs: list[str] = []

    # primitives ---------------------------------------------------------------------------------------------
    def add(self, s: str):
        self.parts.append(s)

    def text(self, x, y, s, size=16, weight=400, fill=None, anchor="start", mono=False, opacity=None, spacing=None):
        fill = fill or self.t["text"]
        fam = MONO if mono else SANS
        extra = (f' opacity="{opacity}"' if opacity is not None else "") + (f' letter-spacing="{spacing}"' if spacing is not None else "")
        self.add(f'<text x="{x}" y="{y}" font-family=\'{fam}\' font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{extra}>{esc(s)}</text>')

    def lines(self, x, y, rows: list[str], size=15, weight=400, fill=None, anchor="start", lh=1.35, mono=False):
        for i, row in enumerate(rows):
            self.text(x, y + i * size * lh, row, size, weight, fill, anchor, mono)

    def rect(self, x, y, w, h, r=16, fill=None, stroke=None, sw=1, shadow=False, opacity=None):
        fill = fill or self.t["card"]
        attrs = f'fill="{fill}"' + (f' stroke="{stroke}" stroke-width="{sw}"' if stroke else "") + (f' opacity="{opacity}"' if opacity is not None else "") + (' filter="url(#sh)"' if shadow else "")
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" {attrs}/>')

    def card(self, x, y, w, h, r=20, fill=None):
        self.rect(x, y, w, h, r, fill=fill, stroke=self.t["edge"], shadow=True)

    def dot(self, cx, cy, r, color):
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>')

    def pill(self, x, y, label, color=None, size=13, weight=600, mono=False, pad=12, h=None, fill=None, anchor="start", text_fill=None):
        w = text_width(label, size, mono, weight) + pad * 2
        h = h or size + 14
        x0 = x - w / 2 if anchor == "middle" else (x - w if anchor == "end" else x)
        color = color or self.t["sub"]
        self.rect(x0, y, w, h, r=h / 2, fill=fill or self.t["chip"])
        self.text(x0 + w / 2, y + h / 2 + size * 0.35, label, size, weight, text_fill or color, "middle", mono)
        return w

    def badge(self, x, y, label, color, size=12):
        w = text_width(label, size, False, 700) + 18
        self.rect(x, y, w, size + 10, r=(size + 10) / 2, fill=color, opacity=0.14)
        self.text(x + w / 2, y + (size + 10) / 2 + size * 0.35, label, size, 700, color, "middle")
        return w

    def arrow(self, x1, y1, x2, y2, color=None, sw=2, head=7):
        color = color or self.t["faint"]
        import math
        a = math.atan2(y2 - y1, x2 - x1)
        bx, by = x2 - math.cos(a) * 1.5, y2 - math.sin(a) * 1.5
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{bx}" y2="{by}" stroke="{color}" stroke-width="{sw}" stroke-linecap="round"/>')
        p1 = (x2 - head * math.cos(a - 0.5), y2 - head * math.sin(a - 0.5))
        p2 = (x2 - head * math.cos(a + 0.5), y2 - head * math.sin(a + 0.5))
        self.add(f'<path d="M{p1[0]:.1f} {p1[1]:.1f} L{x2} {y2} L{p2[0]:.1f} {p2[1]:.1f}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>')

    def elbow(self, x1, y1, x2, y2, color=None, sw=2):
        """Right, then up/down, then right into the target, with rounded corners."""
        color = color or self.t["faint"]
        mid = (x1 + x2) / 2
        r = min(10, abs(y2 - y1) / 2)
        sgn = 1 if y2 > y1 else -1
        d = f"M{x1} {y1} H{mid - r} Q{mid} {y1} {mid} {y1 + sgn * r} V{y2 - sgn * r} Q{mid} {y2} {mid + r} {y2} H{x2 - 2}"
        self.add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round"/>')
        self.add(f'<path d="M{x2 - 7} {y2 - 4} L{x2} {y2} L{x2 - 7} {y2 + 4}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>')

    # output -------------------------------------------------------------------------------------------------
    def svg(self) -> str:
        t = self.t
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" role="img" aria-labelledby="t d">'
            f'<title id="t">{esc(self.title)}</title><desc id="d">{esc(self.desc)}</desc>'
            f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t["bg0"]}"/><stop offset="1" stop-color="{t["bg1"]}"/></linearGradient>'
            f'<filter id="sh" x="-8%" y="-8%" width="116%" height="128%"><feDropShadow dx="0" dy="3" stdDeviation="7" flood-color="#000" flood-opacity="{t["shadow"]}"/></filter>'
            + "".join(self.defs)
            + "</defs>"
            f'<rect width="{self.w}" height="{self.h}" rx="{self.radius}" fill="url(#bg)"/>'
            f'<rect x=".5" y=".5" width="{self.w - 1}" height="{self.h - 1}" rx="{self.radius}" fill="none" stroke="{t["edge"]}"/>'
        )
        return head + "".join(self.parts) + "</svg>\n"


def header(c: Canvas, title: str, subtitle: str, x=56, y=82, size=40):
    c.text(x, y, title, size, 700, c.t["text"], spacing=-0.5)
    c.text(x, y + 34, subtitle, 18, 400, c.t["sub"])


def build(out: Path, name: str, make, *args):
    """make(theme) -> Canvas. Writes <name>-light.svg and <name>-dark.svg."""
    out.mkdir(parents=True, exist_ok=True)
    for theme in ("light", "dark"):
        (out / f"{name}-{theme}.svg").write_text(make(theme, *args).svg(), encoding="utf-8")


def picture(name: str, alt: str, folder="assets", width="100%") -> str:
    return (
        f'<p align="center">\n  <picture>\n'
        f'    <source media="(prefers-color-scheme: dark)" srcset="{folder}/{name}-dark.svg">\n'
        f'    <img src="{folder}/{name}-light.svg" alt="{esc(alt)}" width="{width}">\n'
        f'  </picture>\n</p>\n'
    )


ROOT = Path(__file__).resolve().parent.parent

PALETTE = ["blue", "indigo", "teal", "green", "orange", "pink", "mint", "purple", "cyan", "red", "yellow", "brown"]


def make_tile_grid(theme, title, subtitle, items, unit, alt_desc, note_title, note_body, cols=4):
    """items: [(label, count)]. Counts come from the repository's own files."""
    rows = (len(items) + 1 + cols - 1) // cols
    th, gap, y0 = 132, 16, 168
    W, H = 1200, y0 + rows * th + (rows - 1) * gap + 56
    c = Canvas(W, H, theme, title, alt_desc)
    t = c.t
    c.text(56, 86, title, 44, 700, spacing=-0.8)
    c.text(56, 122, subtitle, 18, 400, t["sub"])
    x0 = 56
    tw = (W - 2 * x0 - gap * (cols - 1)) / cols
    for i, (label, n) in enumerate(items):
        r, k = divmod(i, cols)
        x, y = x0 + k * (tw + gap), y0 + r * (th + gap)
        col = PALETTE[i % len(PALETTE)]
        c.card(x, y, tw, th, 20)
        c.dot(x + 26, y + 30, 6, t[col])
        for j, line in enumerate(wrap(label, 22)[:2]):
            c.text(x + 42, y + 35 + j * 20, line, 16, 600)
        u = unit if n != 1 else unit.rstrip("s")
        c.add(f'<text x="{x + 24}" y="{y + th - 22}" font-family=\'{SANS}\' font-size="40" font-weight="700" fill="{t["ink"].get(col, t[col])}" letter-spacing="-1">{n}<tspan font-size="14" font-weight="500" fill="{t["sub"]}" dx="8" letter-spacing="0">{u}</tspan></text>')
    # the note fills the remaining slot(s) of the last row
    idx = len(items)
    r, k = divmod(idx, cols)
    x, y = x0 + k * (tw + gap), y0 + r * (th + gap)
    w = tw * (cols - k) + gap * (cols - k - 1)
    c.card(x, y, w, th, 20)
    c.text(x + 24, y + 38, note_title, 16, 600)
    for j, line in enumerate(wrap(note_body, max(20, int(w / 8.2)))[:3]):
        c.text(x + 24, y + 64 + j * 21, line, 14, 400, t["sub"])
    return c


def make_pipeline(theme):
    W, H = 1200, 440
    c = Canvas(W, H, theme, "How ConstructBench works",
               "A seed feeds a generator that writes each task and computes its answer; a model answers, with or without a code tool; every field is graded strictly; and results are reported with 95 percent Wilson intervals, per domain and per difficulty.")
    t = c.t
    c.text(56, 84, "Generated. Graded strictly. Reported honestly.", 40, 700, spacing=-0.7)
    c.text(56, 118, "Answers are computed by the same code that wrote the task, so the reference is right by construction.", 17, 400, t["sub"])
    steps = [("1  SEED", "A number", ["Dev seeds are public.", "Held-out seeds are", "kept private."], "blue"),
             ("2  GENERATE", "Task + answer", ["Computed in code from", "the same numbers.", "Images are drawn too."], "indigo"),
             ("3  RUN", "Any model", ["Plain prompt, or with a", "code tool and a strict", "answer schema."], "orange"),
             ("4  GRADE", "Every field", ["Per-field tolerances.", "Strict: all fields right.", "Partial credit reported."], "green"),
             ("5  REPORT", "With error bars", ["95% Wilson intervals,", "paired comparisons,", "per domain and difficulty."], "purple")]
    cw, gap, y, h = 196, 27, 160, 200
    for i, (kick, title, lines, col) in enumerate(steps):
        x = 56 + i * (cw + gap)
        c.card(x, y, cw, h, 22)
        c.rect(x + 20, y + 20, 30, 5, r=2.5, fill=t[col])
        c.text(x + 20, y + 52, kick, 11.5, 700, t["ink"][col], spacing=1)
        c.text(x + 20, y + 84, title, 20, 700, spacing=-0.3)
        c.lines(x + 20, y + 114, lines, 13.5, 400, t["sub"], lh=1.5)
        if i < 4:
            c.arrow(x + cw + 3, y + h / 2, x + cw + gap - 3, y + h / 2, t["faint"], 2, 6)
    c.text(56, 400, "No dependencies to generate and score. Runs are resumable and keep raw responses, so a grader fix re-scores without re-running.", 14, 500, t["sub"])
    return c


def make_effect(theme, rows, n_set):
    """rows: [(model, base_acc, harness_acc)] with accuracies as 0-1 floats, read from the tracked results."""
    W = 1200
    n = len(rows)
    H = 230 + n * 96 + 70
    c = Canvas(W, H, theme, "What a code tool and a strict answer schema do",
               "On the 84-task expert set: " + "; ".join(f"{m} {b * 100:.1f} percent without and {h * 100:.1f} percent with the harness" for m, b, h in rows) + ".")
    t = c.t
    c.text(56, 84, "A code tool closes the gap", 40, 700, spacing=-0.7)
    c.text(56, 118, f"Strict accuracy on the {n_set}-task expert set, without and with the harness (a code tool plus a strict answer schema).", 17, 400, t["sub"])
    # legend
    c.rect(56, 152, 14, 14, r=4, fill=t["faint"]); c.text(78, 164, "No harness", 14, 500, t["sub"])
    c.rect(180, 152, 14, 14, r=4, fill=t["blue"]); c.text(202, 164, "With harness", 14, 500, t["sub"])
    bx, bw = 300, 700
    for i, (model, b, h) in enumerate(rows):
        y = 200 + i * 96
        c.text(56, y + 34, model, 18, 700)
        for k, (v, col, lab) in enumerate(((b, t["faint"], "base"), (h, t["blue"], "harness"))):
            yy = y + k * 34
            c.rect(bx, yy + 8, bw, 22, r=11, fill=t["track"])
            c.rect(bx, yy + 8, max(bw * v, 22), 22, r=11, fill=col)
            c.text(bx + bw + 24, yy + 26, f"{v * 100:.1f}%", 16, 700, t["text"] if k else t["sub"])
    c.card(56, H - 82, W - 112, 54, 16)
    c.text(80, H - 48, "One set, one seed. Claude Opus, Sonnet and Haiku score at or near 100% on the original sets, so they leave little room to show an effect.", 13.5, 500, t["sub"])
    return c


def domain_counts():
    import random, sys
    sys.path.insert(0, str(ROOT))
    from constructbench import registry
    counts = {}
    for name, fn in registry.FAMILIES.items():
        domain = fn(random.Random(1), 0).domain
        counts[domain] = counts.get(domain, 0) + 1
    return counts


def effect_rows():
    import csv
    wanted = {"claude-haiku-5-5": "Claude Haiku 5.5", "deepseek-flash": "DeepSeek Flash", "inclusionai/ling-3.0-flash": "ling-3.0-flash"}
    rows, by = [], {}
    with open(ROOT / "paper" / "report" / "runs.csv", encoding="utf-8", newline="") as h:
        for r in csv.DictReader(h):
            if r["set"] == "expert84-s20261015" and r["model"] in wanted and int(r["runs"]) >= 82:
                by.setdefault(r["model"], {})[r["condition"]] = float(r["accuracy"])
    for model, label in wanted.items():
        if {"base", "harness"} <= set(by.get(model, {})):
            rows.append((label, by[model]["base"], by[model]["harness"]))
    return sorted(rows, key=lambda r: r[1])


if __name__ == "__main__":
    out = ROOT / "assets"
    counts = domain_counts()
    items = sorted(((k.replace("_", " ").capitalize().replace("Bim", "BIM"), v) for k, v in counts.items()), key=lambda kv: (-kv[1], kv[0]))
    total = sum(counts.values())
    build(out, "domains", make_tile_grid, f"{len(counts)} domains, {total} task families", "Every task is generated from a seed, with its answer computed in code.",
          items, "families", f"{total} task families in {len(counts)} domains", "More coming", "Many more data sets, families and tests are on the way.")
    build(out, "how-it-works", make_pipeline)
    build(out, "tool-use-effect", make_effect, effect_rows(), 84)
