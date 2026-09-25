"""Document field extraction: invoices, delivery tickets and lien waivers as a scanned-and-OCR'd page reads.

The noise is the point — remit-to addresses, account numbers, prior balances, a PO number next to the job
number, dates in three formats — because that is what makes real extraction hard and what separates a model
that reads the document from one that grabs the first number.
"""
from __future__ import annotations

import datetime as dt
import random

from ..task import Task, number, TEXT, DATE, answer_keys_line
from .common import JOB_NAMES, VENDORS, job_no, money, pick, r2, round_to

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _date(rng: random.Random) -> dt.date:
    return dt.date(2026, 1, 1) + dt.timedelta(days=rng.randint(0, 300))


def _fmt(d: dt.date, rng: random.Random) -> str:
    style = rng.randint(0, 3)
    if style == 0:
        return f"{d.month:02d}/{d.day:02d}/{d.year % 100:02d}"
    if style == 1:
        return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"
    if style == 2:
        return f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    return d.isoformat()


def invoice(rng: random.Random) -> tuple[str, dict, dict]:
    vendor, job, name = pick(rng, VENDORS), job_no(rng), pick(rng, JOB_NAMES)
    inv = f"{rng.choice(['INV', 'IN', ''])}{rng.randint(10000, 99999)}"
    d = _date(rng)
    lines, sub = [], 0.0
    for _ in range(rng.randint(2, 5)):
        qty = rng.randint(1, 400)
        unit = round(rng.uniform(1.5, 950), 2)
        amt = round(qty * unit, 2)
        sub += amt
        lines.append(f"  {qty:>5}  {pick(rng, ['EA', 'LF', 'SF', 'CY', 'HR', 'LS']):<3} {pick(rng, ['Conduit 3/4 EMT', 'Type X 5/8 board', 'Rebar #5', 'Copper 1in L', 'Labor - journeyman', 'Anchor bolts', 'Duct 12x8', 'Sealant'])[:22]:<22} {unit:>9,.2f} {amt:>12,.2f}")
    sub = round(sub, 2)
    tax_rate = rng.choice([0, 6.25, 7, 8.875])
    tax = round(sub * tax_rate / 100, 2)
    total = round(sub + tax, 2)
    prior = round_to(rng.uniform(2_000, 90_000), 0.01)
    po = f"PO-{rng.randint(4000, 9999)}"
    text = f"""{vendor.upper()}
Remit to: PO Box {rng.randint(100, 9999)}, Lockbox {rng.randint(10000, 99999)}      Acct #{rng.randint(100000, 999999)}

INVOICE                         Invoice No: {inv}
Invoice Date: {_fmt(d, rng)}          Terms: Net {rng.choice([30, 45, 60])}
Ship to: {name} — Job {job}      Customer PO: {po}

   QTY  U/M DESCRIPTION              UNIT PRICE       AMOUNT
{chr(10).join(lines)}

                                   Subtotal     {sub:>12,.2f}
                                   Sales tax    {tax:>12,.2f}
                                   TOTAL DUE    {total:>12,.2f}
Previous balance (not included above): {prior:,.2f}
"""
    fields = {"vendor": TEXT, "invoice_number": TEXT, "invoice_date": DATE, "job_number": TEXT,
              "subtotal": number(0, 0.01), "sales_tax": number(0, 0.01), "total_due": number(0, 0.01)}
    ans = {"vendor": vendor, "invoice_number": inv, "invoice_date": d.isoformat(), "job_number": job,
           "subtotal": sub, "sales_tax": tax, "total_due": total}
    return text, fields, ans


def ticket(rng: random.Random) -> tuple[str, dict, dict]:
    supplier = pick(rng, ["Atlas Ready-Mix", "Granite State Concrete", "Cardinal Lumber", "Keystone Aggregates"])
    tno = f"T-{rng.randint(40000, 89999)}"
    d = _date(rng)
    mat, unit = pick(rng, [("4000 PSI concrete", "CY"), ("3/4in crushed stone", "TON"), ("2x6 SPF #2", "MBF"), ("Rebar #4 grade 60", "TON")])
    qty = round(rng.uniform(4, 60), 1) if unit != "MBF" else round(rng.uniform(1, 9), 2)
    job = job_no(rng)
    text = f"""{supplier}   DELIVERY TICKET {tno}
Plant {rng.randint(1, 9)}   Truck {rng.randint(100, 999)}   Driver: {pick(rng, ['R. Ortiz', 'B. Kim', 'L. Grant'])}
Date {_fmt(d, rng)}   Time out {rng.randint(6, 11)}:{rng.randint(10, 59)}
Deliver to: {pick(rng, JOB_NAMES)}  JOB# {job}   Cust acct {rng.randint(10000, 99999)}
Product: {mat}     Qty this load: {qty} {unit}     Cum. qty today: {round(qty * rng.uniform(1.5, 4), 1)} {unit}
Slump/notes: {rng.choice(['4in', 'n/a', '5in +/- 1'])}      Received by: ____ ({pick(rng, ['J.M.', 'T.B.', 'A.M.'])})
"""
    fields = {"supplier": TEXT, "ticket_number": TEXT, "delivery_date": DATE, "job_number": TEXT, "material": TEXT,
              "quantity": number(0, 0.001), "unit": TEXT}
    return text, fields, {"supplier": supplier, "ticket_number": tno, "delivery_date": d.isoformat(), "job_number": job,
                          "material": mat, "quantity": qty, "unit": unit}


def waiver(rng: random.Random) -> tuple[str, dict, dict]:
    claimant = pick(rng, VENDORS)
    d = _date(rng)
    amount = round_to(rng.uniform(5_000, 480_000), 0.01)
    conditional = rng.random() < .5
    final = rng.random() < .3
    kind = f"{'conditional' if conditional else 'unconditional'} {'final' if final else 'progress'}"
    title = f"{'CONDITIONAL' if conditional else 'UNCONDITIONAL'} WAIVER AND RELEASE ON {'FINAL' if final else 'PROGRESS'} PAYMENT"
    retained = round_to(amount * .1, 0.01)
    text = f"""{title}

Name of Claimant: {claimant}
Name of Customer: {pick(rng, ['Whitfield Construction', 'Sample Contracting Co.', 'Northline Builders'])}
Job Location: {pick(rng, JOB_NAMES)}, Job {job_no(rng)}
Owner: {pick(rng, ['Riverside Housing Partners', 'County School District', 'Harbor Health LLC'])}
Through Date: {_fmt(d, rng)}

This document waives and releases lien rights the claimant has for labor and service provided, and equipment and
material delivered, to the customer on this job through the Through Date, in the amount of $ {amount:,.2f}.
Exceptions: retention of $ {retained:,.2f} and disputed claims for extra work are not covered by this release.
"""
    fields = {"claimant": TEXT, "through_date": DATE, "amount_released": number(0, 0.01), "waiver_type": TEXT}
    return text, fields, {"claimant": claimant, "through_date": d.isoformat(), "amount_released": amount, "waiver_type": kind}


def extraction(rng: random.Random, i: int) -> Task:
    kind = rng.choice(["invoice", "ticket", "waiver"])
    text, fields, ans = {"invoice": invoice, "ticket": ticket, "waiver": waiver}[kind](rng)
    extra = ""
    if kind == "waiver":
        extra = ' For "waiver_type" answer one of: "conditional progress", "unconditional progress", "conditional final", "unconditional final".'
    prompt = ("Extract the fields below from this document, exactly as a construction accounts-payable clerk would enter them. "
              "Dates as YYYY-MM-DD; amounts as plain numbers." + extra + "\n\n--- document (OCR text) ---\n" + text +
              "--- end ---\n" + answer_keys_line(fields))
    return Task(f"doc-{i:04d}", "document_recognition", "extraction", f"Extract fields — {kind}", "medium", prompt, ans, fields, {"kind": kind})
