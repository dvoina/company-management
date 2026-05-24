#!/usr/bin/env python3
"""Local general-ledger helper CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import typer

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent

from double_entry import journal_for_expense, journal_for_invoice, journal_for_payment
from ledger_lib import (
    ensure_ledger,
    load_settings,
    next_expense_id,
    next_invoice_id,
    post_journal_entries,
    read_expenses,
    read_invoices,
    read_journal,
    write_expenses,
    write_invoices,
)

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Basic accounting CLI.")


def _parse_iso_day(value: Optional[str], field_name: str) -> str:
    if not value:
        return str(date.today())
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise typer.BadParameter(f"{field_name} must be YYYY-MM-DD") from exc


def _float(v: str) -> float:
    return float(v or 0)


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        for key, value in payload.items():
            typer.echo(f"{key}: {value}")


def add_income(
    *,
    client: str,
    amount_net: float,
    vat_rate: Optional[float] = None,
    currency: Optional[str] = None,
    invoice_date: Optional[str] = None,
    due_date: Optional[str] = None,
    description: str = "",
    issue_number: str = "cli",
    intra_eu: bool = False,
) -> dict:
    ensure_ledger()
    settings = load_settings()
    inv_date = _parse_iso_day(invoice_date, "date")
    if not due_date:
        terms = int(settings.get("invoice_defaults", {}).get("payment_terms_days", 30))
        due = (datetime.strptime(inv_date, "%Y-%m-%d").date() + timedelta(days=terms)).isoformat()
    else:
        due = _parse_iso_day(due_date, "due-date")

    effective_vat = 0.0 if intra_eu else float(vat_rate if vat_rate is not None else settings["company"]["vat_rate_default"])
    subtotal = round(amount_net, 2)
    vat_amount = round(subtotal * effective_vat / 100, 2)
    total = round(subtotal + vat_amount, 2)

    row = {
        "invoice_id": next_invoice_id(),
        "issue_number": issue_number,
        "client": client,
        "client_cif": "",
        "client_address": "",
        "client_email": "",
        "intra_eu": "Yes" if intra_eu else "No",
        "invoice_date": inv_date,
        "due_date": due,
        "currency": currency or settings["invoice_defaults"]["currency"],
        "subtotal": subtotal,
        "vat_rate": effective_vat,
        "vat_amount": vat_amount,
        "total": total,
        "status": "unpaid",
        "paid_date": "",
        "payment_method": "",
        "bank_account": "",
        "description": description or "Income entry",
        "line_items_json": "[]",
    }

    invoices = read_invoices()
    invoices.append(row)
    write_invoices(invoices)

    entries = journal_for_invoice(row)
    post_journal_entries(entries)

    return {
        "invoice_id": row["invoice_id"],
        "client": row["client"],
        "total": row["total"],
        "currency": row["currency"],
        "journal_entries": len(entries),
    }


def add_expense(
    *,
    supplier: str,
    amount_net: float,
    vat_amount: float = 0.0,
    category: str = "Other",
    currency: Optional[str] = None,
    expense_date: Optional[str] = None,
    description: str = "",
    issue_number: str = "cli",
    payment_method: str = "",
) -> dict:
    ensure_ledger()
    settings = load_settings()
    cats = settings.get("expense_categories", {})
    gl_account = cats.get(category, {}).get("account", settings["saft"]["accounts"]["expenses_services"])
    entry_date = _parse_iso_day(expense_date, "date")
    total = round(float(amount_net) + float(vat_amount), 2)

    row = {
        "expense_id": next_expense_id(),
        "issue_number": issue_number,
        "date": entry_date,
        "supplier_name": supplier,
        "supplier_cif": "",
        "supplier_country": "",
        "intra_eu": "No",
        "invoice_ref": "",
        "amount_net": round(float(amount_net), 2),
        "vat_amount": round(float(vat_amount), 2),
        "total": total,
        "currency": currency or settings["invoice_defaults"]["currency"],
        "category": category,
        "description": description or "Expense entry",
        "payment_method": payment_method,
        "tax_deductible": "Yes",
        "gl_account": gl_account,
    }

    expenses = read_expenses()
    expenses.append(row)
    write_expenses(expenses)

    entries = journal_for_expense(row)
    post_journal_entries(entries)

    return {
        "expense_id": row["expense_id"],
        "supplier_name": row["supplier_name"],
        "total": row["total"],
        "currency": row["currency"],
        "journal_entries": len(entries),
    }


def mark_invoice_paid(invoice_id: str, paid_date: Optional[str] = None) -> dict:
    ensure_ledger()
    paid = _parse_iso_day(paid_date, "paid-date")
    invoices = read_invoices()
    for invoice in invoices:
        if invoice.get("invoice_id") != invoice_id:
            continue
        if invoice.get("status") == "paid":
            return {"invoice_id": invoice_id, "status": "already_paid", "journal_entries": 0}

        invoice["status"] = "paid"
        invoice["paid_date"] = paid
        write_invoices(invoices)
        entries = journal_for_payment(invoice)
        post_journal_entries(entries)
        return {"invoice_id": invoice_id, "status": "paid", "journal_entries": len(entries)}

    raise ValueError(f"invoice not found: {invoice_id}")


def build_summary() -> dict:
    ensure_ledger()
    invoices = read_invoices()
    expenses = read_expenses()
    journal = read_journal()

    billed = sum(_float(row.get("total")) for row in invoices)
    paid = sum(_float(row.get("total")) for row in invoices if row.get("status") == "paid")
    outstanding = sum(_float(row.get("total")) for row in invoices if row.get("status") == "unpaid")
    spent = sum(_float(row.get("total")) or (_float(row.get("amount_net")) + _float(row.get("vat_amount"))) for row in expenses)
    debits = sum(_float(row.get("debit")) for row in journal)
    credits = sum(_float(row.get("credit")) for row in journal)

    return {
        "invoices": len(invoices),
        "expenses": len(expenses),
        "journal_entries": len(journal),
        "total_billed": round(billed, 2),
        "total_paid": round(paid, 2),
        "total_outstanding": round(outstanding, 2),
        "total_expenses": round(spent, 2),
        "trial_balance_diff": round(debits - credits, 2),
    }


@app.command("income")
def income_command(
    client: str = typer.Option(..., "--client"),
    amount_net: float = typer.Option(..., "--amount-net"),
    vat_rate: Optional[float] = typer.Option(None, "--vat-rate"),
    currency: Optional[str] = typer.Option(None, "--currency"),
    invoice_date: Optional[str] = typer.Option(None, "--date"),
    due_date: Optional[str] = typer.Option(None, "--due-date"),
    description: str = typer.Option("", "--description"),
    issue_number: str = typer.Option("cli", "--issue-number"),
    intra_eu: bool = typer.Option(False, "--intra-eu"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    result = add_income(
        client=client,
        amount_net=amount_net,
        vat_rate=vat_rate,
        currency=currency,
        invoice_date=invoice_date,
        due_date=due_date,
        description=description,
        issue_number=issue_number,
        intra_eu=intra_eu,
    )
    _emit(result, as_json)


@app.command("expense")
def expense_command(
    supplier: str = typer.Option(..., "--supplier"),
    amount_net: float = typer.Option(..., "--amount-net"),
    vat_amount: float = typer.Option(0.0, "--vat-amount"),
    category: str = typer.Option("Other", "--category"),
    currency: Optional[str] = typer.Option(None, "--currency"),
    expense_date: Optional[str] = typer.Option(None, "--date"),
    description: str = typer.Option("", "--description"),
    issue_number: str = typer.Option("cli", "--issue-number"),
    payment_method: str = typer.Option("", "--payment-method"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    result = add_expense(
        supplier=supplier,
        amount_net=amount_net,
        vat_amount=vat_amount,
        category=category,
        currency=currency,
        expense_date=expense_date,
        description=description,
        issue_number=issue_number,
        payment_method=payment_method,
    )
    _emit(result, as_json)


@app.command("pay")
def pay_command(
    invoice_id: str = typer.Option(..., "--invoice-id"),
    paid_date: Optional[str] = typer.Option(None, "--paid-date"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    try:
        result = mark_invoice_paid(invoice_id=invoice_id, paid_date=paid_date)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    _emit(result, as_json)


@app.command("summary")
def summary_command(as_json: bool = typer.Option(False, "--json")) -> None:
    _emit(build_summary(), as_json)


@app.command("validate")
def validate_command() -> None:
    _run_script("validate_ledger.py")


def _run_script(script_name: str, *args: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        typer.echo(proc.stdout.strip())
    if proc.stderr:
        typer.echo(proc.stderr.strip(), err=True)
    if proc.returncode:
        raise typer.Exit(proc.returncode)


@app.command("plan-validate")
def plan_validate_command() -> None:
    _run_script("account_plan.py", "validate")


@app.command("plan-tree")
def plan_tree_command(
    markdown: bool = typer.Option(False, "--markdown"),
    output: Optional[str] = typer.Option(None, "--output"),
) -> None:
    args = ["tree"]
    if markdown:
        args.append("--markdown")
    if output:
        args.extend(["--output", output])
    _run_script("account_plan.py", *args)


if __name__ == "__main__":
    app()
