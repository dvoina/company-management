"""
Shared ledger utilities — reads settings.yml, manages all CSV files.
"""

import csv
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT       = Path(__file__).parent.parent
LEDGER_DIR = ROOT / "ledger"
SCRIPTS_DIR= ROOT / "scripts"

INVOICES_CSV = LEDGER_DIR / "invoices.csv"
EXPENSES_CSV = LEDGER_DIR / "expenses.csv"
JOURNAL_CSV  = LEDGER_DIR / "journal.csv"
ACCOUNT_PLAN_YML = LEDGER_DIR / "account_plan.yml"

INVOICE_FIELDS = [
    "invoice_id", "issue_number", "client", "client_cif", "client_address",
    "client_email", "intra_eu", "invoice_date", "due_date", "currency",
    "subtotal", "vat_rate", "vat_amount", "total",
    "status", "paid_date", "payment_method", "bank_account",
    "description", "line_items_json",
]

EXPENSE_FIELDS = [
    "expense_id", "issue_number", "date", "supplier_name", "supplier_cif",
    "supplier_country", "intra_eu", "invoice_ref", "amount_net", "vat_amount",
    "total", "currency", "category", "description", "payment_method",
    "tax_deductible", "gl_account",
]

JOURNAL_FIELDS = [
    "entry_id", "date", "description",
    "account_code", "account_name",
    "debit", "credit", "currency",
    "source_type", "source_id",  # e.g. "invoice" / "INV-001"
]


def load_settings():
    path = ROOT / "settings.yml"
    if not path.exists():
        raise FileNotFoundError("settings.yml not found in repo root")
    with open(path) as f:
        return yaml.safe_load(f)


def load_account_plan():
    if not ACCOUNT_PLAN_YML.exists():
        raise FileNotFoundError(f"{ACCOUNT_PLAN_YML} not found")
    with open(ACCOUNT_PLAN_YML, encoding="utf-8") as f:
        plan = yaml.safe_load(f) or {}
    if not isinstance(plan, dict):
        raise ValueError("account_plan.yml must contain a YAML object at root")
    return plan


def account_plan_index(plan=None):
    plan = plan or load_account_plan()
    rows = plan.get("accounts") or []
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").strip()
        if code:
            out[code] = row
    return out


def account_name(code, fallback=""):
    key = str(code or "").strip()
    if not key:
        return fallback
    row = account_plan_index().get(key)
    if not row:
        return fallback
    return str(row.get("name") or fallback)


def ensure_ledger():
    LEDGER_DIR.mkdir(exist_ok=True)
    for path, fields in [
        (INVOICES_CSV, INVOICE_FIELDS),
        (EXPENSES_CSV, EXPENSE_FIELDS),
        (JOURNAL_CSV,  JOURNAL_FIELDS),
    ]:
        if not path.exists():
            with open(path, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=fields).writeheader()


def _read(path, fields):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def _write(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def read_invoices():  return _read(INVOICES_CSV, INVOICE_FIELDS)
def read_expenses():  return _read(EXPENSES_CSV, EXPENSE_FIELDS)
def read_journal():   return _read(JOURNAL_CSV,  JOURNAL_FIELDS)

def write_invoices(rows): _write(INVOICES_CSV, INVOICE_FIELDS, rows)
def write_expenses(rows): _write(EXPENSES_CSV, EXPENSE_FIELDS, rows)
def write_journal(rows):  _write(JOURNAL_CSV,  JOURNAL_FIELDS, rows)


def next_id(rows, field, prefix):
    nums = []
    for r in rows:
        m = re.match(rf"{re.escape(prefix)}-(\d+)", r.get(field, ""))
        if m:
            nums.append(int(m.group(1)))
    return f"{prefix}-{(max(nums)+1 if nums else 1):03d}"

def next_invoice_id(): return next_id(read_invoices(), "invoice_id", load_settings()["invoice_defaults"]["series"])
def next_expense_id(): return next_id(read_expenses(), "expense_id", "EXP")
def next_entry_id():   return next_id(read_journal(),  "entry_id",   "JNL")


def parse_amount(s):
    cleaned = re.sub(r"[^\d.]", "", str(s or "0")).lstrip(".")
    return float(cleaned or 0)


def extract_field(body, label):
    pattern = rf"\*\*{re.escape(label)}[:\*]{{0,2}}\s*(.+)"
    m = re.search(pattern, body, re.IGNORECASE)
    if m:
        val = re.sub(r"<!--.*?-->", "", m.group(1)).strip()
        return val or ""
    return ""


def extract_line_items(body):
    """Parse the line items markdown table into a list of dicts."""
    items = []
    in_table = False
    for line in body.splitlines():
        if "| Description" in line:
            in_table = True
            continue
        if in_table and "|---" in line:
            continue
        if in_table and "|" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 4 and "<!--" not in parts[0]:
                try:
                    items.append({
                        "description": parts[0],
                        "qty":         float(re.sub(r"[^\d.]", "", parts[1]) or 1),
                        "unit_price":  parse_amount(parts[2]),
                        "vat_pct":     float(re.sub(r"[^\d.]", "", parts[3]) or 19),
                        "line_total":  parse_amount(parts[4]) if len(parts) > 4 else 0,
                    })
                except (ValueError, IndexError):
                    pass
        elif in_table and line.strip() == "":
            break
    return items


def post_journal_entries(entries):
    """Append journal entries, auto-assigning IDs."""
    rows = read_journal()
    counter_start = len(rows) + 1
    for i, e in enumerate(entries):
        if not e.get("entry_id"):
            e["entry_id"] = f"JNL-{counter_start + i:04d}"
    rows.extend(entries)
    write_journal(rows)
    return entries
