"""
mark_paid.py
Finds the invoice row matching the issue number and marks it paid.
"""

import os
from datetime import date
from ledger_lib import ensure_ledger, read_invoices, write_invoices


def main():
    ensure_ledger()
    issue_number = os.environ.get("ISSUE_NUMBER", "0")
    paid_date = os.environ.get("PAID_DATE", str(date.today()))[:10]

    rows = read_invoices()
    found = False
    for row in rows:
        if row["issue_number"] == issue_number:
            row["status"] = "paid"
            row["paid_date"] = paid_date
            found = True
            print(f"Marked paid: {row['invoice_id']} — {row['client']} — {row['total']} {row['currency']}")
            break

    if not found:
        print(f"Warning: no invoice found for issue #{issue_number}")

    write_invoices(rows)


if __name__ == "__main__":
    main()
