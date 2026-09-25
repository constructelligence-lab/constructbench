"""Job-cost finance: earned value, WIP / over-under billing, change-order pricing, retainage."""
from __future__ import annotations

import random

from ..task import Task, number, TEXT, answer_keys_line
from .common import JOB_NAMES, job_no, money, pick, r2, r4, round_to


def evm(rng: random.Random, i: int) -> Task:
    bac = round_to(rng.uniform(0.8e6, 9e6), 10_000)
    sched = rng.randint(20, 80)
    done = max(5, min(95, sched + rng.randint(-12, 6)))
    ev = bac * done / 100
    ac = round_to(ev * rng.uniform(0.85, 1.25), 1_000)
    pv = bac * sched / 100
    cpi, spi = ev / ac, ev / pv
    eac = bac / cpi
    tcpi = (bac - ev) / (bac - ac)
    fields = {"cpi": number(abs_tol=0.005), "spi": number(abs_tol=0.005), "eac": number(0.002), "vac": number(0.01, 1000),
              "tcpi": number(abs_tol=0.005)}
    name, no = pick(rng, JOB_NAMES), job_no(rng)
    prompt = (f"Job {no} ({name}) has a budget at completion of {money(bac)}. By today the schedule planned "
              f"{sched}% of the work to be complete; the superintendent's quantity count says {done}% is actually complete. "
              f"Actual cost to date from the job cost ledger is {money(ac)}.\n\n"
              "Using standard earned value management, compute the cost performance index (CPI), the schedule "
              "performance index (SPI), the estimate at completion using EAC = BAC / CPI, the variance at completion "
              "expressed as EAC − BAC (positive means over budget), and the to-complete performance index "
              "TCPI = (BAC − EV) / (BAC − AC).\n" + answer_keys_line(fields))
    return Task(f"evm-{i:04d}", "project_management", "evm", "Earned value indices", "easy", prompt,
                {"cpi": r4(cpi), "spi": r4(spi), "eac": r2(eac), "vac": r2(eac - bac), "tcpi": r4(tcpi)}, fields)


def wip(rng: random.Random, i: int) -> Task:
    # Several jobs; percentage of completion by cost-to-cost; over/under billing per job and the most under-billed.
    n = rng.randint(3, 5)
    names = rng.sample(JOB_NAMES, n)
    rows, out = [], {}
    worst, worst_v = None, 0.0
    total_ob = 0.0
    for k, nm in enumerate(names):
        contract = round_to(rng.uniform(0.6e6, 6e6), 5_000)
        est_cost = round_to(contract * rng.uniform(0.80, 0.97), 1_000)
        ctd = round_to(est_cost * rng.uniform(0.15, 0.9), 500)
        pct = ctd / est_cost
        earned = contract * pct
        # At least one job is genuinely under-billed, so "most under-billed" always names one.
        billed = round_to(earned * (rng.uniform(0.82, 0.95) if k == 0 else rng.uniform(0.85, 1.12)), 500)
        ob = billed - earned
        total_ob += ob
        if worst is None or ob < worst_v:
            worst, worst_v = nm, ob
        rows.append((nm, contract, est_cost, ctd, billed))
    rng.shuffle(rows)
    table = "\n".join(f"| {nm} | {money(c)} | {money(e)} | {money(t)} | {money(b)} |" for nm, c, e, t, b in rows)
    fields = {"net_over_under_billing": number(0.002, 50), "most_underbilled_job": TEXT, "most_underbilled_amount": number(0.002, 50)}
    prompt = ("A contractor's work-in-progress schedule for the month:\n\n"
              "| Job | Contract value | Estimated total cost | Cost to date | Billed to date |\n|---|---|---|---|---|\n" + table + "\n\n"
              "Recognise revenue by percentage of completion using the cost-to-cost method (cost to date ÷ estimated total "
              "cost). Over/under billing is billed to date minus earned revenue: positive is over-billed, negative is under-billed.\n"
              "Give the net over/under billing across all jobs, the name of the most under-billed job (the most negative "
              "over/under figure), and that job's under-billing as a positive amount.\n" + answer_keys_line(fields))
    return Task(f"wip-{i:04d}", "finance", "wip", "WIP schedule and over/under billing", "medium", prompt,
                {"net_over_under_billing": r2(total_ob), "most_underbilled_job": worst, "most_underbilled_amount": r2(-worst_v)}, fields)


def change_order(rng: random.Random, i: int) -> Task:
    hrs = rng.randint(40, 600)
    rate = rng.choice([48, 52, 56.5, 61, 64.25, 72])
    burden = rng.choice([28, 32, 35, 38, 42])
    mat = round_to(rng.uniform(2_000, 60_000), 50)
    sub = round_to(rng.uniform(0, 120_000), 100)
    equip = round_to(rng.uniform(0, 9_000), 25)
    oh_own = rng.choice([10, 12, 15])
    fee_own = rng.choice([5, 8, 10])
    mk_sub = rng.choice([5, 7.5, 10])
    bond = rng.choice([0.8, 1.0, 1.25, 1.5])
    labor = hrs * rate * (1 + burden / 100)
    own = labor + mat + equip
    own_oh = own * oh_own / 100
    own_fee = (own + own_oh) * fee_own / 100
    sub_mk = sub * mk_sub / 100
    subtotal = own + own_oh + own_fee + sub + sub_mk
    bond_amt = subtotal * bond / 100
    total = subtotal + bond_amt
    fields = {"labor_cost": number(0.001, 1), "subtotal_before_bond": number(0.001, 1), "change_order_price": number(0.001, 1)}
    prompt = (f"Price a change order for job {job_no(rng)} under these contract terms.\n\n"
              f"Self-performed work: {hrs} labor hours at a base wage of ${rate:,.2f}/hour plus labor burden of {burden}% of wages; "
              f"material {money(mat)}; owned equipment {money(equip)}.\nSubcontracted work: {money(sub)}.\n\n"
              f"Markups, in this order: overhead of {oh_own}% on self-performed cost; then fee of {fee_own}% on self-performed "
              f"cost plus its overhead; {mk_sub}% markup on subcontracted work; then a bond premium of {bond}% on the total of "
              "everything above.\nGive the burdened labor cost, the subtotal before bond, and the change order price.\n"
              + answer_keys_line(fields))
    return Task(f"co-{i:04d}", "estimating", "change_orders", "Change order pricing with markups", "medium", prompt,
                {"labor_cost": r2(labor), "subtotal_before_bond": r2(subtotal), "change_order_price": r2(total)}, fields)


def retainage(rng: random.Random, i: int) -> Task:
    contract = round_to(rng.uniform(1.5e6, 12e6), 10_000)
    r1 = rng.choice([10, 10, 5])
    r2_ = rng.choice([5, 2.5]) if r1 == 10 else 2.5
    trigger = 50
    pct_done = rng.randint(55, 92)
    completed = contract * pct_done / 100
    new_work_only = rng.random() < 0.5
    at_trigger = contract * trigger / 100
    if new_work_only:
        held = at_trigger * r1 / 100 + (completed - at_trigger) * r2_ / 100
        rule = (f"Once the work reaches {trigger}% complete, retainage on work performed after that point drops to {r2_}%; "
                f"retainage already held on the first {trigger}% stays at {r1}%.")
    else:
        held = completed * r2_ / 100
        rule = (f"Once the work reaches {trigger}% complete, retainage on the entire completed balance is recalculated at "
                f"{r2_}% and the excess is released.")
    prev_paid = round_to((completed - held) * rng.uniform(0.82, 0.95), 1_000)
    due = completed - held - prev_paid
    fields = {"retainage_held": number(0.001, 1), "current_payment_due": number(0.001, 1)}
    prompt = (f"A {money(contract)} contract carries {r1}% retainage. {rule}\n\n"
              f"This pay application brings total completed and stored to date to {pct_done}% of the contract. "
              f"Previous payments received total {money(prev_paid)}.\n"
              "Give the retainage held after this application and the current payment due (completed to date, less "
              "retainage, less previous payments).\n" + answer_keys_line(fields))
    return Task(f"ret-{i:04d}", "finance", "retainage", "Retainage and payment due", "medium", prompt,
                {"retainage_held": r2(held), "current_payment_due": r2(due)}, fields, {"rule": "new_work_only" if new_work_only else "whole_balance"})
