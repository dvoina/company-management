"""
register_invoice.py — parse invoice issue, write ledger row, post journal entries.
"""
import json, os
from datetime import date
import typer
from ledger_lib import (
    ensure_ledger, read_invoices, write_invoices,
    next_invoice_id, parse_amount, extract_field, extract_line_items,
    post_journal_entries, load_settings, LEDGER_DIR,
)
from double_entry import journal_for_invoice


def main():
    ensure_ledger()
    body         = os.environ.get("ISSUE_BODY", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "0")
    created_at   = os.environ.get("ISSUE_DATE", str(date.today()))[:10]
    s            = load_settings()

    line_items = extract_line_items(body)
    subtotal   = sum(i["line_total"] or i["qty"] * i["unit_price"] for i in line_items)
    vat_amount = sum((i["line_total"] or i["qty"] * i["unit_price"]) * i["vat_pct"] / 100 for i in line_items)
    total      = subtotal + vat_amount
    vat_rate   = round(vat_amount / subtotal * 100, 1) if subtotal else s["company"]["vat_rate_default"]

    # Fall back to explicit totals if line items were empty / not parsed
    if not line_items:
        subtotal   = parse_amount(extract_field(body, "Subtotal.*"))
        vat_amount = parse_amount(extract_field(body, "VAT Amount"))
        total      = parse_amount(extract_field(body, "Total"))
        vat_rate   = s["company"]["vat_rate_default"]

    intra_eu = extract_field(body, "Intra-EU").lower().startswith("y")
    if intra_eu:
        vat_amount = 0
        vat_rate   = 0
        total      = subtotal

    row = {
        "invoice_id":      next_invoice_id(),
        "issue_number":    issue_number,
        "client":          extract_field(body, "Client Name"),
        "client_cif":      extract_field(body, "Client CIF.*"),
        "client_address":  extract_field(body, "Client Address"),
        "client_email":    extract_field(body, "Client Email"),
        "intra_eu":        "Yes" if intra_eu else "No",
        "invoice_date":    extract_field(body, "Invoice Date") or created_at,
        "due_date":        extract_field(body, "Due Date"),
        "currency":        extract_field(body, "Currency") or s["invoice_defaults"]["currency"],
        "subtotal":        round(subtotal, 2),
        "vat_rate":        vat_rate,
        "vat_amount":      round(vat_amount, 2),
        "total":           round(total, 2),
        "status":          "unpaid",
        "paid_date":       "",
        "payment_method":  extract_field(body, "Payment Method"),
        "bank_account":    extract_field(body, "Bank Account"),
        "description":     line_items[0]["description"] if line_items else extract_field(body, "Notes"),
        "line_items_json": json.dumps(line_items),
    }

    rows = read_invoices()
    rows.append(row)
    write_invoices(rows)

    entries = journal_for_invoice(row)
    post_journal_entries(entries)

    LEDGER_DIR.joinpath("last_action.txt").write_text(row["invoice_id"])
    print(f"Registered: {row['invoice_id']} — {row['client']} — {row['total']} {row['currency']}")
    print(f"Posted {len(entries)} journal entries")


if __name__ == "__main__":
    typer.run(main)
