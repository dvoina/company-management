"""
double_entry.py
Generates journal entries (double-entry) for invoices and expenses.
Called after register_invoice.py and log_expense.py.
"""

import json
from datetime import date
from ledger_lib import load_settings, post_journal_entries


def journal_for_invoice(inv):
    """
    When invoice is raised:
      DR  4111  Clients (receivable)        total
      CR  704   Revenue                     subtotal
      CR  4427  TVA colectată               vat_amount

    When invoice is paid:
      DR  5121/5124  Bank                   total
      CR  4111       Clients                total
    """
    s        = load_settings()
    accts    = s["saft"]["accounts"]
    currency = inv.get("currency", "RON")
    desc     = inv.get("client", "")
    inv_id   = inv["invoice_id"]
    total    = float(inv.get("total") or 0)
    subtotal = float(inv.get("subtotal") or 0)
    vat      = float(inv.get("vat_amount") or 0)
    inv_date = inv.get("invoice_date", str(date.today()))

    entries = [
        # Debit receivable
        {
            "date": inv_date, "description": f"Invoice {inv_id} — {desc}",
            "account_code": accts["receivables"], "account_name": "Clienți",
            "debit": total, "credit": 0,
            "currency": currency, "source_type": "invoice", "source_id": inv_id,
        },
        # Credit revenue
        {
            "date": inv_date, "description": f"Invoice {inv_id} — {desc}",
            "account_code": accts["revenue_services"], "account_name": "Venituri din servicii",
            "debit": 0, "credit": subtotal,
            "currency": currency, "source_type": "invoice", "source_id": inv_id,
        },
    ]
    if vat:
        entries.append({
            "date": inv_date, "description": f"TVA colectată {inv_id}",
            "account_code": accts["vat_collected"], "account_name": "TVA colectată",
            "debit": 0, "credit": vat,
            "currency": currency, "source_type": "invoice", "source_id": inv_id,
        })
    return entries


def journal_for_payment(inv):
    s        = load_settings()
    accts    = s["saft"]["accounts"]
    currency = inv.get("currency", "RON")
    inv_id   = inv["invoice_id"]
    total    = float(inv.get("total") or 0)
    paid_date= inv.get("paid_date", str(date.today()))
    bank_acct= accts["bank_eur"] if currency == "EUR" else accts["bank_ron"]

    return [
        # Debit bank
        {
            "date": paid_date, "description": f"Payment received {inv_id}",
            "account_code": bank_acct, "account_name": "Cont bancar",
            "debit": total, "credit": 0,
            "currency": currency, "source_type": "payment", "source_id": inv_id,
        },
        # Credit receivable
        {
            "date": paid_date, "description": f"Payment received {inv_id}",
            "account_code": accts["receivables"], "account_name": "Clienți",
            "debit": 0, "credit": total,
            "currency": currency, "source_type": "payment", "source_id": inv_id,
        },
    ]


def journal_for_expense(exp):
    """
    When expense is recorded:
      DR  628/625/…   Expense account        net
      DR  4426        TVA deductibilă        vat
      CR  401         Furnizori              total

    When expense is paid:
      DR  401         Furnizori              total
      CR  5121/5311   Bank / Cash            total
    """
    s        = load_settings()
    accts    = s["saft"]["accounts"]
    cats     = s.get("expense_categories", {})
    currency = exp.get("currency", "RON")
    exp_id   = exp["expense_id"]
    net      = float(exp.get("amount_net") or 0)
    vat      = float(exp.get("vat_amount") or 0)
    total    = float(exp.get("total") or net + vat)
    exp_date = exp.get("date", str(date.today()))
    cat      = exp.get("category", "Other")
    desc     = exp.get("description", "")
    gl_acct  = exp.get("gl_account") or cats.get(cat, {}).get("account", accts["expenses_services"])

    entries = [
        # Debit expense
        {
            "date": exp_date, "description": f"Expense {exp_id} — {desc}",
            "account_code": gl_acct, "account_name": f"Cheltuieli {cat}",
            "debit": net, "credit": 0,
            "currency": currency, "source_type": "expense", "source_id": exp_id,
        },
        # Credit payable
        {
            "date": exp_date, "description": f"Expense {exp_id} — {exp.get('supplier_name','')}",
            "account_code": accts["payables"], "account_name": "Furnizori",
            "debit": 0, "credit": total,
            "currency": currency, "source_type": "expense", "source_id": exp_id,
        },
    ]
    if vat:
        entries.append({
            "date": exp_date, "description": f"TVA deductibilă {exp_id}",
            "account_code": accts["vat_deductible"], "account_name": "TVA deductibilă",
            "debit": vat, "credit": 0,
            "currency": currency, "source_type": "expense", "source_id": exp_id,
        })
    return entries
