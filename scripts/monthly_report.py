"""
monthly_report.py
Generates a markdown P&L report for the previous month (or a specified month).
Writes to generated/reports/YYYY-MM.md
"""

import os
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

# Allow running from repo root or scripts/
sys.path.insert(0, str(Path(__file__).parent))
from ledger_lib import read_invoices, read_expenses, LEDGER_DIR

REPORTS_DIR = Path(__file__).parent.parent / "generated" / "reports"


def get_target_month():
    override = os.environ.get("REPORT_MONTH", "").strip()
    if override:
        return override[:7]  # YYYY-MM
    today = date.today()
    # Last month
    month = today.month - 1 or 12
    year  = today.year if today.month > 1 else today.year - 1
    return f"{year}-{month:02d}"


def filter_by_month(rows, date_field, ym):
    return [r for r in rows if r.get(date_field, "").startswith(ym)]


def fmt(amount, currency="EUR"):
    return f"{float(amount or 0):,.2f} {currency}"


def main():
    ym = get_target_month()
    year, month = ym.split("-")
    month_name = datetime(int(year), int(month), 1).strftime("%B %Y")

    invoices = read_invoices()
    expenses = read_expenses()

    # Revenue: paid invoices in this month (by paid_date)
    paid = filter_by_month(invoices, "paid_date", ym)
    # Billed: invoices raised in this month (regardless of payment)
    billed = filter_by_month(invoices, "invoice_date", ym)
    # Expenses in this month
    month_expenses = filter_by_month(expenses, "date", ym)

    total_received  = sum(float(r["total"] or 0) for r in paid)
    total_billed    = sum(float(r["total"] or 0) for r in billed)
    total_expenses  = sum(float(r["amount"] or 0) for r in month_expenses)
    net             = total_received - total_expenses

    # Expenses by category
    by_cat = defaultdict(float)
    for r in month_expenses:
        by_cat[r["category"] or "Other"] += float(r["amount"] or 0)

    # Outstanding invoices (unpaid)
    outstanding = [r for r in invoices if r["status"] == "unpaid"]
    total_outstanding = sum(float(r["total"] or 0) for r in outstanding)

    lines = [
        f"# Monthly Report — {month_name}",
        f"> Generated: {date.today()}",
        "",
        "## 💰 Revenue",
        "",
        f"| | Amount |",
        f"|---|---|",
        f"| Billed this month | {fmt(total_billed)} |",
        f"| **Received this month** | **{fmt(total_received)}** |",
        "",
    ]

    if paid:
        lines += ["### Payments received", ""]
        lines += ["| Invoice | Client | Amount | Paid Date |", "|---|---|---|---|"]
        for r in paid:
            lines.append(f"| {r['invoice_id']} | {r['client']} | {fmt(r['total'])} | {r['paid_date']} |")
        lines.append("")

    lines += [
        "## 📤 Expenses",
        "",
        f"**Total: {fmt(total_expenses)}**",
        "",
        "| Category | Amount |",
        "|---|---|",
    ]
    for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        lines.append(f"| {cat} | {fmt(amt)} |")
    lines.append("")

    if month_expenses:
        lines += ["### Expense detail", ""]
        lines += ["| ID | Date | Vendor | Description | Amount |", "|---|---|---|---|---|"]
        for r in month_expenses:
            lines.append(f"| {r['expense_id']} | {r['date']} | {r['vendor']} | {r['description']} | {fmt(r['amount'])} |")
        lines.append("")

    lines += [
        "## 📊 Net",
        "",
        f"| | |",
        f"|---|---|",
        f"| Revenue received | {fmt(total_received)} |",
        f"| Expenses | -{fmt(total_expenses)} |",
        f"| **Net** | **{fmt(net)}** |",
        "",
    ]

    if outstanding:
        lines += [
            "## ⏳ Outstanding Invoices",
            "",
            f"**{len(outstanding)} invoice(s) unpaid — {fmt(total_outstanding)} total**",
            "",
            "| Invoice | Client | Total | Due Date |",
            "|---|---|---|---|",
        ]
        for r in outstanding:
            overdue = ""
            if r["due_date"] and r["due_date"] < str(date.today()):
                overdue = " ⚠️ overdue"
            lines.append(f"| {r['invoice_id']} | {r['client']} | {fmt(r['total'])} | {r['due_date']}{overdue} |")
        lines.append("")

    report = "\n".join(lines)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"{ym}.md"
    out_path.write_text(report)
    print(f"Report written to {out_path}")

    # Also write a plain summary for the Actions step summary
    summary = (
        f"**{month_name}** | "
        f"Received: {fmt(total_received)} | "
        f"Expenses: {fmt(total_expenses)} | "
        f"Net: {fmt(net)}"
    )
    (LEDGER_DIR / "summary.txt").write_text(summary)


if __name__ == "__main__":
    main()
