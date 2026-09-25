"""Shared helpers for generators: formatting, rounding, and invented names.

All names are invented. Job numbers use the J-NNNN form on purpose — no year-and-sequence numbers that
could look like a real contractor's.
"""
from __future__ import annotations

import random

JOB_NAMES = ["Riverside Apartments", "Harbourview Clinic", "Foundry Lofts", "Cedar Ridge School", "Mason Street Retail",
             "Northgate Distribution", "Elm Park Library", "Summit Hotel Renovation", "Birchwood Senior Living",
             "Quarry Market Hall", "Lakeside Surgical Center", "Kingsley High Gym", "Station Plaza Garage",
             "Alder House Condominiums", "Westbrook Fire Station", "Pier 9 Office Fit-Out"]
VENDORS = ["Copperline Mechanical", "Voltline Electric", "Granite State Concrete", "Summit Drywall & Acoustics",
           "Bayside Glass", "Ironwood Steel Erectors", "Northfield Plumbing", "Keystone Roofing", "Atlas Ready-Mix",
           "Cardinal Lumber", "Harbor Crane & Rigging", "Pinnacle Fire Protection"]
PEOPLE = ["A. Morgan", "P. Raman", "M. Lee", "S. Alvarez", "T. Becker", "R. Patel", "E. O'Neill", "C. Duval",
          "J. Okafor", "L. Novak", "D. Whitfield", "K. Tanaka"]


def job_no(rng: random.Random) -> str:
    return f"J-{rng.randint(1001, 1999)}"


def money(v: float, cents: bool = False) -> str:
    return f"${v:,.2f}" if cents else f"${v:,.0f}"


def r2(v: float) -> float:
    return round(v + 0.0, 2)


def r4(v: float) -> float:
    return round(v + 0.0, 4)


def pick(rng: random.Random, xs: list):
    return xs[rng.randrange(len(xs))]


def round_to(v: float, step: float) -> float:
    return round(v / step) * step
