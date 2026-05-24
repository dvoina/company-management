"""
register_invoice.py
Parses a GitHub issue body (invoice template) and appends a row to invoices.csv
"""

import os
import re
from datetime import date
from ledger_lib import (
    ensure_ledger, read_invoices, write_invoices,
    next_invoice_id, parse_amount, extract_field,
    LEDGER_DIR,
)


def parse_issue():
    body = os.environ.get("ISSUE_BODY", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "0")
    created_at = os.environ.get("ISSUE_DATE", str(date.today()))[:10]

    client       = extract_field(body, "Client")
    client_email = extract_field(body, "Client Email")
    inv_date     = extract_field(body, "Invoice Date") or created_at
    due_date     = extract_field(body, "Due Date")
    currency     = extract_field(body, "Currency") or "EUR"
    vat_line     = extract_field(body, "VAT.*")

    # Parse totals from the summary lines
    subtotal_str = extract_field(body, "Subtotal")
    total_str    = extract_field(body, "Total")
    vat_str      = re.search(r"\*\*VAT.*?\*\*:?\s*([\d.,]+)", body)

    subtotal  = parse_amount(subtotal_str)
    total     = parse_amount(total_str)
    vat_amount = parse_amount(vat_str.group(1)) if vat_str else round(total - subtotal, 2)
    vat_rate  = round(vat_amount / subtotal * 100, 1) if subtotal else 0.0

    # First line item description (first non-header, non-empty table row)
    desc = ""
    for line in body.splitlines():
        if "|" in line and "---" not in line and "Description" not in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if parts and parts[0] and "<!--" not in parts[0]:
                desc = parts[0]
                break

    return {
        "invoice_id":   next_invoice_id(),
        "issue_number": issue_number,
        "client":       client,
        "client_email": client_email,
        "invoice_date": inv_date,
        "due_date":     due_date,
        "currency":     currency,
        "subtotal":     subtotal,
        "vat_rate":     vat_rate,
        "vat_amount":   vat_amount,
        "total":        total,
        "status":       "unpaid",
        "paid_date":    "",
        "description":  desc,
    }


def main():
    ensure_ledger()
    row = parse_issue()
    rows = read_invoices()
    rows.append(row)
    write_invoices(rows)

    # Write last action for the comment step
    (LEDGER_DIR / "last_action.txt").write_text(row["invoice_id"])
    print(f"Registered: {row['invoice_id']} — {row['client']} — {row['total']} {row['currency']}")


if __name__ == "__main__":
    main()
