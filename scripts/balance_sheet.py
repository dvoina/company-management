"""
balance_sheet.py
Generates a markdown balance sheet for the target month.
Writes to generated/reports/YYYY-MM-balance-sheet.md
"""

from __future__ import annotations

import sys
from calendar import monthrange
from collections import defaultdict
from datetime import date
from pathlib import Path
import typer

sys.path.insert(0, str(Path(__file__).parent))
from ledger_lib import load_settings, read_journal
from monthly_report import get_target_month

REPORTS_DIR = Path(__file__).parent.parent / "generated" / "reports"


def parse_amount(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def fmt(amount, currency):
    return f"{float(amount or 0):,.2f} {currency}"


def month_end_date(ym):
    year, month = (int(p) for p in ym.split("-"))
    return date(year, month, monthrange(year, month)[1]).isoformat()


def startswith_any(value, prefixes):
    return any(value.startswith(prefix) for prefix in prefixes if prefix)


def classify_account(code, account_prefixes, settings):
    if code.startswith(("6", "7")):
        return "pnl"

    if startswith_any(code, account_prefixes["assets"]):
        return "assets"
    if startswith_any(code, account_prefixes["liabilities"]):
        return "liabilities"
    if startswith_any(code, account_prefixes["equity"]):
        return "equity"

    accounts = settings["saft"]["accounts"]
    if startswith_any(code, [accounts.get("receivables", ""), accounts.get("vat_deductible", "")]):
        return "assets"
    if startswith_any(code, [accounts.get("payables", ""), accounts.get("vat_collected", ""), accounts.get("vat_payable", "")]):
        return "liabilities"
    if startswith_any(code, [accounts.get("cash", ""), accounts.get("bank_ron", ""), accounts.get("bank_eur", "")]):
        return "assets"
    if code.startswith(("2", "3", "5")):
        return "assets"
    if code.startswith("1"):
        return "equity"
    return "unclassified"


def add_table(lines, title, rows, currency):
    lines.extend([f"### {title}", "", "| Account | Name | Amount |", "|---|---|---|"])
    if not rows:
        lines.append(f"| — | — | {fmt(0, currency)} |")
    else:
        for account_code, account_name, amount in rows:
            lines.append(f"| {account_code} | {account_name} | {fmt(amount, currency)} |")
    lines.append("")


def main():
    ym = get_target_month()
    cutoff = month_end_date(ym)
    settings = load_settings()
    currency = settings["invoice_defaults"]["currency"]

    cfg_prefixes = settings.get("balance_sheet", {}).get("account_prefixes", {})
    account_prefixes = {
        "assets": cfg_prefixes.get("assets", []),
        "liabilities": cfg_prefixes.get("liabilities", []),
        "equity": cfg_prefixes.get("equity", []),
    }

    journal_rows = [row for row in read_journal() if (row.get("date") or "")[:10] <= cutoff]

    balances = defaultdict(lambda: {"name": "", "balance": 0.0})
    for row in journal_rows:
        account_code = (row.get("account_code") or "").strip()
        if not account_code:
            continue
        balances[account_code]["name"] = row.get("account_name") or balances[account_code]["name"] or "Unknown account"
        balances[account_code]["balance"] += parse_amount(row.get("debit")) - parse_amount(row.get("credit"))

    assets = []
    liabilities = []
    equity = []
    unclassified = []
    revenues = 0.0
    expenses = 0.0

    for account_code, data in sorted(balances.items()):
        balance = round(data["balance"], 2)
        if abs(balance) < 0.005:
            continue

        account_name = data["name"]
        classification = classify_account(account_code, account_prefixes, settings)

        if classification == "pnl":
            if account_code.startswith("7"):
                revenues += -balance
            elif account_code.startswith("6"):
                expenses += balance
            continue

        if classification == "assets":
            if balance >= 0:
                assets.append((account_code, account_name, balance))
            else:
                liabilities.append((account_code, f"{account_name} (contra)", -balance))
        elif classification in ("liabilities", "equity"):
            target = liabilities if classification == "liabilities" else equity
            if balance <= 0:
                target.append((account_code, account_name, -balance))
            else:
                assets.append((account_code, f"{account_name} (contra)", balance))
        else:
            side = "debit" if balance >= 0 else "credit"
            unclassified.append((account_code, f"{account_name} ({side})", abs(balance)))

    current_result = round(revenues - expenses, 2)
    if abs(current_result) >= 0.005:
        equity.append(("P&L", "Current year result", current_result))

    total_assets = sum(row[2] for row in assets)
    total_liabilities = sum(row[2] for row in liabilities)
    total_equity = sum(row[2] for row in equity)
    rhs_total = total_liabilities + total_equity
    imbalance = round(total_assets - rhs_total, 2)

    lines = [
        f"# Balance Sheet — {ym}",
        f"> As of: {cutoff}",
        f"> Generated: {date.today()}",
        "",
        f"Journal lines included: **{len(journal_rows)}**",
        "",
    ]

    add_table(lines, "Assets", assets, currency)
    add_table(lines, "Liabilities", liabilities, currency)
    add_table(lines, "Equity", equity, currency)

    if unclassified:
        lines.extend([
            "### Unclassified accounts",
            "",
            "These accounts were not mapped by default classification rules.",
            "Set explicit prefixes in `settings.yml` under `balance_sheet.account_prefixes`.",
            "",
            "| Account | Name | Balance |",
            "|---|---|---|",
        ])
        for account_code, account_name, amount in unclassified:
            lines.append(f"| {account_code} | {account_name} | {fmt(amount, currency)} |")
        lines.append("")

    lines.extend([
        "## Totals",
        "",
        "| | Amount |",
        "|---|---|",
        f"| Total assets | {fmt(total_assets, currency)} |",
        f"| Total liabilities | {fmt(total_liabilities, currency)} |",
        f"| Total equity | {fmt(total_equity, currency)} |",
        f"| Liabilities + Equity | {fmt(rhs_total, currency)} |",
        f"| **Imbalance** | **{fmt(imbalance, currency)}** |",
        "",
    ])

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"{ym}-balance-sheet.md"
    out_path.write_text("\n".join(lines))
    print(f"Balance sheet written to {out_path}")


if __name__ == "__main__":
    typer.run(main)
