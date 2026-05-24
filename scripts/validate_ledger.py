"""
validate_ledger.py
Sanity-checks invoices.csv and expenses.csv.
Exits with code 1 if critical errors are found.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from ledger_lib import read_invoices, read_expenses
from datetime import date

errors   = []
warnings = []

def check_invoices():
    rows = read_invoices()
    seen_ids = set()
    for i, r in enumerate(rows, 1):
        inv_id = r.get("invoice_id", "")

        if inv_id in seen_ids:
            errors.append(f"Row {i}: duplicate invoice_id '{inv_id}'")
        seen_ids.add(inv_id)

        try:
            total    = float(r.get("total") or 0)
            subtotal = float(r.get("subtotal") or 0)
            vat      = float(r.get("vat_amount") or 0)
        except ValueError:
            errors.append(f"{inv_id}: non-numeric amount")
            continue

        if total < 0:
            errors.append(f"{inv_id}: negative total {total}")

        if abs((subtotal + vat) - total) > 0.02:
            warnings.append(f"{inv_id}: subtotal {subtotal} + vat {vat} ≠ total {total}")

        status = r.get("status", "")
        if status not in ("unpaid", "paid", "overdue", "cancelled"):
            warnings.append(f"{inv_id}: unknown status '{status}'")

        if status == "unpaid" and r.get("due_date"):
            if r["due_date"] < str(date.today()):
                warnings.append(f"{inv_id}: overdue (due {r['due_date']}), still marked 'unpaid'")

        if status == "paid" and not r.get("paid_date"):
            warnings.append(f"{inv_id}: status is 'paid' but no paid_date set")


def check_expenses():
    rows = read_expenses()
    seen_ids = set()
    for i, r in enumerate(rows, 1):
        exp_id = r.get("expense_id", "")

        if exp_id in seen_ids:
            errors.append(f"Row {i}: duplicate expense_id '{exp_id}'")
        seen_ids.add(exp_id)

        try:
            amount = float(r.get("amount") or 0)
        except ValueError:
            errors.append(f"{exp_id}: non-numeric amount")
            continue

        if amount < 0:
            errors.append(f"{exp_id}: negative amount {amount}")

        if not r.get("date"):
            warnings.append(f"{exp_id}: missing date")


def main():
    check_invoices()
    check_expenses()

    if warnings:
        print("⚠️  Warnings:")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        print("\n❌ Errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"✅ Ledger valid — {len(read_invoices())} invoices, {len(read_expenses())} expenses")


if __name__ == "__main__":
    main()
