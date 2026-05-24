"""
Shared ledger utilities.
All CSV files use a consistent schema so scripts can interoperate.
"""

import csv
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

LEDGER_DIR = Path(__file__).parent.parent / "ledger"
INVOICES_CSV = LEDGER_DIR / "invoices.csv"
EXPENSES_CSV = LEDGER_DIR / "expenses.csv"

INVOICE_FIELDS = [
    "invoice_id", "issue_number", "client", "client_email",
    "invoice_date", "due_date", "currency",
    "subtotal", "vat_rate", "vat_amount", "total",
    "status",       # unpaid | paid | overdue | cancelled
    "paid_date",
    "description",  # first line item description
]

EXPENSE_FIELDS = [
    "expense_id", "issue_number", "date", "amount", "currency",
    "category", "vendor", "description", "tax_deductible",
]


def ensure_ledger():
    LEDGER_DIR.mkdir(exist_ok=True)
    if not INVOICES_CSV.exists():
        with open(INVOICES_CSV, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=INVOICE_FIELDS).writeheader()
    if not EXPENSES_CSV.exists():
        with open(EXPENSES_CSV, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=EXPENSE_FIELDS).writeheader()


def read_invoices():
    if not INVOICES_CSV.exists():
        return []
    with open(INVOICES_CSV, newline="") as f:
        return list(csv.DictReader(f))


def write_invoices(rows):
    with open(INVOICES_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INVOICE_FIELDS)
        w.writeheader()
        w.writerows(rows)


def read_expenses():
    if not EXPENSES_CSV.exists():
        return []
    with open(EXPENSES_CSV, newline="") as f:
        return list(csv.DictReader(f))


def write_expenses(rows):
    with open(EXPENSES_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EXPENSE_FIELDS)
        w.writeheader()
        w.writerows(rows)


def next_invoice_id():
    rows = read_invoices()
    if not rows:
        return "INV-001"
    nums = []
    for r in rows:
        m = re.match(r"INV-(\d+)", r.get("invoice_id", ""))
        if m:
            nums.append(int(m.group(1)))
    n = max(nums) + 1 if nums else 1
    return f"INV-{n:03d}"


def next_expense_id():
    rows = read_expenses()
    if not rows:
        return "EXP-001"
    nums = []
    for r in rows:
        m = re.match(r"EXP-(\d+)", r.get("expense_id", ""))
        if m:
            nums.append(int(m.group(1)))
    n = max(nums) + 1 if nums else 1
    return f"EXP-{n:03d}"


def parse_amount(s):
    """Strip currency symbols/spaces and return float."""
    return float(re.sub(r"[^\d.]", "", str(s)) or 0)


def extract_field(body, label):
    """Extract **Label:** value from markdown issue body."""
    pattern = rf"\*\*{re.escape(label)}:\*\*\s*(.+)"
    m = re.search(pattern, body, re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        # Strip markdown comments
        val = re.sub(r"<!--.*?-->", "", val).strip()
        return val if val else ""
    return ""
