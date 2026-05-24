"""mark_paid.py — mark invoice paid and post payment journal entries."""
import os
from datetime import date
from ledger_lib import ensure_ledger, read_invoices, write_invoices, post_journal_entries
from double_entry import journal_for_payment


def main():
    ensure_ledger()
    issue_number = os.environ.get("ISSUE_NUMBER", "0")
    paid_date    = os.environ.get("PAID_DATE", str(date.today()))[:10]

    rows  = read_invoices()
    found = None
    for row in rows:
        if row["issue_number"] == issue_number:
            row["status"]    = "paid"
            row["paid_date"] = paid_date
            found = row
            break

    if not found:
        print(f"Warning: no invoice for issue #{issue_number}")
        return

    write_invoices(rows)
    entries = journal_for_payment(found)
    post_journal_entries(entries)
    print(f"Marked paid: {found['invoice_id']} — posted {len(entries)} journal entries")


if __name__ == "__main__":
    main()
