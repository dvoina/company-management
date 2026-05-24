"""
saft_export.py
Generates a SAF-T (D406) XML file conforming to the ANAF Romania schema.
Covers: Header, MasterFiles (Accounts, Customers, Suppliers),
        GeneralLedgerEntries, SalesInvoices, PurchaseInvoices.

Usage:
    python scripts/saft_export.py --period 2025-05
    python scripts/saft_export.py --period 2025      # full year
    python scripts/saft_export.py                    # last month
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, indent, tostring
from xml.dom import minidom

sys.path.insert(0, str(Path(__file__).parent))
from ledger_lib import (
    account_name, load_settings, read_invoices, read_expenses, read_journal,
)

OUTPUT_DIR = Path(__file__).parent.parent / "generated" / "saft"

# ANAF SAF-T namespace
NS  = "urn:StandardAuditFile-Taxation-Financial:RO"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = f"{NS} https://static.anaf.ro/static/10/Anaf/Declaratii_R/Declaratia406/D406_v2.xsd"


def fmt_date(d):
    """Ensure YYYY-MM-DD."""
    if not d:
        return ""
    return str(d)[:10]


def fmt_amount(v):
    try:
        return f"{float(v or 0):.2f}"
    except (ValueError, TypeError):
        return "0.00"


def period_filter(rows, date_field, period):
    """Filter rows by period string: 'YYYY-MM' or 'YYYY'."""
    return [r for r in rows if r.get(date_field, "").startswith(period)]


def get_vat_code(vat_rate, intra_eu, settings):
    codes = settings["saft"]["vat_codes"]
    if str(intra_eu).lower().startswith("y"):
        return codes["reverse_charge"]
    rate = float(vat_rate or 0)
    if rate >= 19:   return codes["standard"]
    if rate >= 9:    return codes["reduced_9"]
    if rate >= 5:    return codes["reduced_5"]
    return codes["exempt"]


def build_xml(period, settings, invoices, expenses, journal):
    s  = settings["company"]
    sa = settings["saft"]["accounts"]

    root = Element("AuditFile")
    root.set("xmlns",              NS)
    root.set("xmlns:xsi",          XSI)
    root.set("xsi:schemaLocation", SCHEMA_LOCATION)

    # ── Header ────────────────────────────────────────────────────────────────
    hdr = SubElement(root, "Header")
    SubElement(hdr, "AuditFileVersion").text      = "2.0"
    SubElement(hdr, "AuditFileCountry").text       = "RO"
    SubElement(hdr, "AuditFileDateCreated").text   = str(date.today())
    SubElement(hdr, "SoftwareCompanyName").text    = "github-company-os"
    SubElement(hdr, "SoftwareID").text             = "github-actions"
    SubElement(hdr, "SoftwareVersion").text        = "1.0"

    co = SubElement(hdr, "Company")
    SubElement(co, "RegistrationNumber").text      = s["cif"]
    SubElement(co, "Name").text                    = s["name"]

    addr = SubElement(co, "Address")
    SubElement(addr, "StreetName").text            = s["address"]["street"]
    SubElement(addr, "City").text                  = s["address"]["city"]
    SubElement(addr, "PostalCode").text            = s["address"]["postal_code"]
    SubElement(addr, "Country").text               = s["address"]["country"]

    SubElement(co, "TaxRegistrationNumber").text   = s["cif"]
    SubElement(co, "OrganizationType").text        = s["type"]

    fsp = SubElement(hdr, "SelectionCriteria")
    SubElement(fsp, "SelectionStartDate").text = f"{period}-01" if len(period) == 7 else f"{period}-01-01"
    # End date: last day of period
    if len(period) == 7:
        import calendar
        y, m = int(period[:4]), int(period[5:7])
        last = calendar.monthrange(y, m)[1]
        SubElement(fsp, "SelectionEndDate").text = f"{period}-{last:02d}"
    else:
        SubElement(fsp, "SelectionEndDate").text = f"{period}-12-31"

    SubElement(hdr, "NumberOfParts").text = "1"
    SubElement(hdr, "PartNumber").text    = "1"

    # ── MasterFiles ───────────────────────────────────────────────────────────
    mf = SubElement(root, "MasterFiles")

    # Chart of Accounts
    accts_used = {
        sa["revenue_services"]: account_name(sa["revenue_services"], "Venituri din servicii prestate"),
        sa["receivables"]:      account_name(sa["receivables"], "Clienți"),
        sa["payables"]:         account_name(sa["payables"], "Furnizori"),
        sa["vat_collected"]:    account_name(sa["vat_collected"], "TVA colectată"),
        sa["vat_deductible"]:   account_name(sa["vat_deductible"], "TVA deductibilă"),
        sa["vat_payable"]:      account_name(sa["vat_payable"], "TVA de plată"),
        sa["bank_ron"]:         account_name(sa["bank_ron"], "Conturi la bănci în lei"),
        sa["bank_eur"]:         account_name(sa["bank_eur"], "Conturi la bănci în valută"),
        sa["expenses_services"]: account_name(sa["expenses_services"], "Cheltuieli cu servicii"),
        sa["expenses_travel"]:  account_name(sa["expenses_travel"], "Cheltuieli deplasări"),
    }
    # Add GL accounts from journal
    for jrow in journal:
        code = jrow.get("account_code", "")
        name = jrow.get("account_name", "")
        if code and code not in accts_used:
            accts_used[code] = account_name(code, name)

    gla = SubElement(mf, "GeneralLedgerAccounts")
    for code, name in sorted(accts_used.items()):
        acc = SubElement(gla, "Account")
        SubElement(acc, "AccountID").text          = code
        SubElement(acc, "AccountDescription").text = name
        SubElement(acc, "AccountType").text        = "GL"
        SubElement(acc, "AccountCreationDate").text= str(date.today())
        SubElement(acc, "OpeningDebitBalance").text= "0.00"
        SubElement(acc, "OpeningCreditBalance").text="0.00"

    # Customers (from invoices)
    customers_seen = {}
    for inv in invoices:
        cif = inv.get("client_cif") or inv.get("client", "UNKNOWN")
        if cif not in customers_seen:
            customers_seen[cif] = inv

    custs = SubElement(mf, "Customers")
    for cif, inv in customers_seen.items():
        cust = SubElement(custs, "Customer")
        SubElement(cust, "CustomerID").text             = cif
        SubElement(cust, "CustomerTaxID").text          = cif
        SubElement(cust, "CompanyName").text            = inv.get("client", "")
        addr2 = SubElement(cust, "BillingAddress")
        SubElement(addr2, "StreetName").text            = inv.get("client_address", "")
        SubElement(addr2, "Country").text               = "RO"
        SubElement(cust, "Contact").text                = inv.get("client_email", "")

    # Suppliers (from expenses)
    suppliers_seen = {}
    for exp in expenses:
        cif = exp.get("supplier_cif") or exp.get("supplier_name", "UNKNOWN")
        if cif not in suppliers_seen:
            suppliers_seen[cif] = exp

    supps = SubElement(mf, "Suppliers")
    for cif, exp in suppliers_seen.items():
        sup = SubElement(supps, "Supplier")
        SubElement(sup, "SupplierID").text              = cif
        SubElement(sup, "SupplierTaxID").text           = cif
        SubElement(sup, "CompanyName").text             = exp.get("supplier_name", "")
        addr3 = SubElement(sup, "BillingAddress")
        SubElement(addr3, "Country").text               = exp.get("supplier_country", "RO")

    # ── GeneralLedgerEntries ─────────────────────────────────────────────────
    gle = SubElement(root, "GeneralLedgerEntries")

    # Group journal rows by date (one "transaction" per date+source)
    by_source = defaultdict(list)
    for jrow in journal:
        key = (jrow.get("source_type",""), jrow.get("source_id",""))
        by_source[key].append(jrow)

    total_debit = total_credit = 0.0
    num_entries = 0

    for (src_type, src_id), jrows in sorted(by_source.items()):
        txn = SubElement(gle, "Journal")
        SubElement(txn, "JournalID").text          = src_id
        SubElement(txn, "Description").text        = f"{src_type} {src_id}"
        SubElement(txn, "Type").text               = "GL"

        for jrow in jrows:
            line = SubElement(txn, "Transaction")
            SubElement(line, "TransactionID").text = jrow.get("entry_id", "")
            SubElement(line, "Period").text        = jrow.get("date", "")[:7].replace("-", "")
            SubElement(line, "TransactionDate").text = fmt_date(jrow.get("date"))
            SubElement(line, "Description").text   = jrow.get("description", "")
            SubElement(line, "SystemEntryDate").text = str(date.today())

            ln = SubElement(line, "Line")
            SubElement(ln, "RecordID").text        = jrow.get("entry_id", "")
            SubElement(ln, "AccountID").text       = jrow.get("account_code", "")
            debit  = float(jrow.get("debit")  or 0)
            credit = float(jrow.get("credit") or 0)
            SubElement(ln, "DebitAmount").text     = fmt_amount(debit)
            SubElement(ln, "CreditAmount").text    = fmt_amount(credit)
            SubElement(ln, "Description").text     = jrow.get("description", "")
            total_debit  += debit
            total_credit += credit
            num_entries  += 1

    SubElement(gle, "NumberOfEntries").text       = str(num_entries)
    SubElement(gle, "TotalDebit").text            = fmt_amount(total_debit)
    SubElement(gle, "TotalCredit").text           = fmt_amount(total_credit)

    # ── SalesInvoices ─────────────────────────────────────────────────────────
    si = SubElement(root, "SourceDocuments")
    sales = SubElement(si, "SalesInvoices")
    SubElement(sales, "NumberOfEntries").text     = str(len(invoices))
    SubElement(sales, "TotalDebit").text          = fmt_amount(sum(float(r.get("total") or 0) for r in invoices))
    SubElement(sales, "TotalCredit").text         = "0.00"

    for inv in invoices:
        doc = SubElement(sales, "Invoice")
        SubElement(doc, "InvoiceNo").text          = inv["invoice_id"]
        SubElement(doc, "CustomerID").text         = inv.get("client_cif") or inv.get("client","")
        SubElement(doc, "InvoiceDate").text        = fmt_date(inv.get("invoice_date"))
        SubElement(doc, "InvoiceType").text        = "380"  # UN/EDIFACT: commercial invoice
        SubElement(doc, "SpecialCircumstances").text = "RC" if inv.get("intra_eu","").lower().startswith("y") else ""
        SubElement(doc, "SelfBillingIndicator").text = "0"
        SubElement(doc, "CashVATSchemeIndicator").text = "0"

        period_el = SubElement(doc, "Period")
        SubElement(period_el, "PeriodStartDate").text = fmt_date(inv.get("invoice_date"))
        SubElement(period_el, "PeriodEndDate").text   = fmt_date(inv.get("due_date"))

        line_items = []
        try:
            raw = inv.get("line_items_json") or "[]"
            line_items = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            pass

        if not line_items:
            line_items = [{"description": inv.get("description",""), "qty": 1,
                           "unit_price": float(inv.get("subtotal") or 0),
                           "vat_pct": float(inv.get("vat_rate") or 0),
                           "line_total": float(inv.get("subtotal") or 0)}]

        for idx, item in enumerate(line_items, 1):
            ln = SubElement(doc, "Line")
            SubElement(ln, "LineNumber").text      = str(idx)
            SubElement(ln, "ProductDescription").text = item.get("description","")
            qty = SubElement(ln, "Quantity")
            qty.text                               = fmt_amount(item.get("qty", 1))
            SubElement(ln, "UnitOfMeasure").text   = "EA"
            SubElement(ln, "UnitPrice").text       = fmt_amount(item.get("unit_price", 0))
            SubElement(ln, "TaxPointDate").text    = fmt_date(inv.get("invoice_date"))

            refs = SubElement(ln, "References")
            SubElement(refs, "InvoiceRef").text    = inv["invoice_id"]

            tax = SubElement(ln, "Tax")
            SubElement(tax, "TaxType").text        = "TVA"
            SubElement(tax, "TaxCode").text        = get_vat_code(
                item.get("vat_pct", inv.get("vat_rate",0)),
                inv.get("intra_eu","No"),
                settings,
            )
            SubElement(tax, "TaxPercentage").text  = fmt_amount(item.get("vat_pct", inv.get("vat_rate",0)))
            line_net = item.get("line_total") or item.get("qty",1) * item.get("unit_price",0)
            SubElement(tax, "TaxBase").text        = fmt_amount(line_net)
            SubElement(tax, "TaxAmount").text      = fmt_amount(line_net * float(item.get("vat_pct", inv.get("vat_rate",0))) / 100)

            SubElement(ln, "LineAmount").text      = fmt_amount(line_net)

        doc_totals = SubElement(doc, "DocumentTotals")
        SubElement(doc_totals, "TaxPayable").text      = fmt_amount(inv.get("vat_amount"))
        SubElement(doc_totals, "NetTotal").text        = fmt_amount(inv.get("subtotal"))
        SubElement(doc_totals, "GrossTotal").text      = fmt_amount(inv.get("total"))

    # ── PurchaseInvoices ──────────────────────────────────────────────────────
    purchases = SubElement(si, "PurchaseInvoices")
    SubElement(purchases, "NumberOfEntries").text  = str(len(expenses))
    SubElement(purchases, "TotalDebit").text       = "0.00"
    SubElement(purchases, "TotalCredit").text      = fmt_amount(sum(float(r.get("total") or 0) for r in expenses))

    for exp in expenses:
        doc = SubElement(purchases, "Invoice")
        SubElement(doc, "InvoiceNo").text          = exp.get("invoice_ref") or exp["expense_id"]
        SubElement(doc, "SupplierID").text         = exp.get("supplier_cif") or exp.get("supplier_name","")
        SubElement(doc, "InvoiceDate").text        = fmt_date(exp.get("date"))
        SubElement(doc, "InvoiceType").text        = "380"

        ln = SubElement(doc, "Line")
        SubElement(ln, "LineNumber").text          = "1"
        SubElement(ln, "ProductDescription").text  = exp.get("description","")
        SubElement(ln, "Quantity").text            = "1.00"
        SubElement(ln, "UnitOfMeasure").text       = "EA"
        SubElement(ln, "UnitPrice").text           = fmt_amount(exp.get("amount_net"))
        SubElement(ln, "TaxPointDate").text        = fmt_date(exp.get("date"))

        tax = SubElement(ln, "Tax")
        SubElement(tax, "TaxType").text            = "TVA"
        # Derive VAT rate from net/vat amounts
        net = float(exp.get("amount_net") or 0)
        vat = float(exp.get("vat_amount") or 0)
        rate = round(vat / net * 100, 1) if net else 0
        SubElement(tax, "TaxCode").text            = get_vat_code(rate, exp.get("intra_eu","No"), settings)
        SubElement(tax, "TaxPercentage").text      = fmt_amount(rate)
        SubElement(tax, "TaxBase").text            = fmt_amount(net)
        SubElement(tax, "TaxAmount").text          = fmt_amount(vat)
        SubElement(ln, "LineAmount").text          = fmt_amount(net)

        doc_totals = SubElement(doc, "DocumentTotals")
        SubElement(doc_totals, "TaxPayable").text  = fmt_amount(exp.get("vat_amount"))
        SubElement(doc_totals, "NetTotal").text    = fmt_amount(exp.get("amount_net"))
        SubElement(doc_totals, "GrossTotal").text  = fmt_amount(exp.get("total"))

    return root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", help="YYYY-MM or YYYY", default=None)
    args = parser.parse_args()

    if args.period:
        period = args.period
    else:
        # Default: last month
        today = date.today()
        m = today.month - 1 or 12
        y = today.year if today.month > 1 else today.year - 1
        period = f"{y}-{m:02d}"

    settings  = load_settings()
    all_inv   = read_invoices()
    all_exp   = read_expenses()
    all_jnl   = read_journal()

    date_field_inv = "invoice_date"
    date_field_exp = "date"
    date_field_jnl = "date"

    invoices = period_filter(all_inv, date_field_inv, period)
    expenses = period_filter(all_exp, date_field_exp, period)
    journal  = period_filter(all_jnl, date_field_jnl, period)

    print(f"Period: {period} — {len(invoices)} invoices, {len(expenses)} expenses, {len(journal)} journal lines")

    root = build_xml(period, settings, invoices, expenses, journal)

    indent(root, space="  ")
    xml_bytes = tostring(root, encoding="unicode", xml_declaration=False)
    xml_out   = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"D406_{period.replace('-','')}.xml"
    out_path.write_text(xml_out, encoding="utf-8")
    print(f"SAF-T written to: {out_path}")


if __name__ == "__main__":
    main()
