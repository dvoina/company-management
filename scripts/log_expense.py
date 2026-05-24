"""
log_expense.py
Parses a GitHub expense issue and appends to expenses.csv
"""

import os
from ledger_lib import (
    ensure_ledger, read_expenses, write_expenses,
    next_expense_id, parse_amount, extract_field,
)


def main():
    ensure_ledger()
    body         = os.environ.get("ISSUE_BODY", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "0")

    exp_date    = extract_field(body, "Date")
    amount      = parse_amount(extract_field(body, "Amount"))
    currency    = extract_field(body, "Currency") or "EUR"
    category    = extract_field(body, "Category")
    vendor      = extract_field(body, "Vendor")
    description = extract_field(body, "Description")
    tax_ded     = extract_field(body, "Tax Deductible")

    row = {
        "expense_id":    next_expense_id(),
        "issue_number":  issue_number,
        "date":          exp_date,
        "amount":        amount,
        "currency":      currency,
        "category":      category,
        "vendor":        vendor,
        "description":   description,
        "tax_deductible": tax_ded,
    }

    rows = read_expenses()
    rows.append(row)
    write_expenses(rows)

    print(f"Logged: {row['expense_id']} — {row['vendor']} — {row['amount']} {row['currency']} ({row['category']})")


if __name__ == "__main__":
    main()
