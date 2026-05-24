"""log_expense.py — parse expense issue, log it, post journal entries."""
import os
import typer
from ledger_lib import (
    ensure_ledger, read_expenses, write_expenses,
    next_expense_id, parse_amount, extract_field,
    post_journal_entries, load_settings,
)
from double_entry import journal_for_expense


def main():
    ensure_ledger()
    body         = os.environ.get("ISSUE_BODY", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "0")
    s            = load_settings()
    cats         = s.get("expense_categories", {})

    category = extract_field(body, "Category")
    gl_acct  = cats.get(category, {}).get("account", s["saft"]["accounts"]["expenses_services"])
    amount_net  = parse_amount(extract_field(body, r"Amount.*ex\. VAT.*") or extract_field(body, "Amount"))
    vat_amount  = parse_amount(extract_field(body, "VAT Amount"))
    total       = parse_amount(extract_field(body, "Total"))
    if not total:
        total = amount_net + vat_amount

    row = {
        "expense_id":       next_expense_id(),
        "issue_number":     issue_number,
        "date":             extract_field(body, "Date"),
        "supplier_name":    extract_field(body, "Supplier Name"),
        "supplier_cif":     extract_field(body, "Supplier CIF.*"),
        "supplier_country": extract_field(body, "Supplier Country"),
        "intra_eu":         extract_field(body, "Intra-EU"),
        "invoice_ref":      extract_field(body, "Invoice.*Receipt Number"),
        "amount_net":       amount_net,
        "vat_amount":       vat_amount,
        "total":            total,
        "currency":         extract_field(body, "Currency") or s["invoice_defaults"]["currency"],
        "category":         category,
        "description":      extract_field(body, "Description"),
        "payment_method":   extract_field(body, "Payment Method"),
        "tax_deductible":   extract_field(body, "Tax Deductible"),
        "gl_account":       gl_acct,
    }

    rows = read_expenses()
    rows.append(row)
    write_expenses(rows)

    entries = journal_for_expense(row)
    post_journal_entries(entries)
    print(f"Logged: {row['expense_id']} — {row['supplier_name']} — {row['total']} {row['currency']}")
    print(f"Posted {len(entries)} journal entries")


if __name__ == "__main__":
    typer.run(main)
