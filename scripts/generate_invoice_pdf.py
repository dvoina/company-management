"""
generate_invoice_pdf.py
Render a branded invoice PDF from ledger/invoices.csv and optionally sign it.
"""

import argparse
import json
import os
from pathlib import Path

from ledger_lib import ROOT, LEDGER_DIR, ensure_ledger, load_settings, read_invoices

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
except ImportError as exc:
    raise RuntimeError(
        "Missing dependency: reportlab. Install with `pip install reportlab`."
    ) from exc


def parse_args():
    parser = argparse.ArgumentParser(description="Generate invoice PDF from ledger row")
    parser.add_argument("--invoice-id", help="Invoice ID, e.g. FCT-001")
    parser.add_argument("--output", help="Output PDF path (default: generated/invoices/<id>.pdf)")
    return parser.parse_args()


def to_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def is_enabled(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_path(path_value):
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def load_invoice(invoice_id):
    rows = read_invoices()
    for row in rows:
        if row.get("invoice_id") == invoice_id:
            return row
    raise ValueError(f"Invoice not found: {invoice_id}")


def invoice_id_from_context(cli_invoice_id):
    if cli_invoice_id:
        return cli_invoice_id

    env_invoice_id = os.environ.get("INVOICE_ID")
    if env_invoice_id:
        return env_invoice_id

    marker = LEDGER_DIR / "last_action.txt"
    if marker.exists():
        value = marker.read_text(encoding="utf-8").strip()
        if value:
            return value

    raise ValueError("No invoice ID provided and ledger/last_action.txt is empty.")


def parse_items(row):
    raw = row.get("line_items_json", "")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list) and data:
                items = []
                for item in data:
                    qty = to_float(item.get("qty"), 1)
                    unit_price = to_float(item.get("unit_price"), 0)
                    line_total = to_float(item.get("line_total"), qty * unit_price)
                    items.append(
                        {
                            "description": str(item.get("description", "")).strip() or "Item",
                            "qty": qty,
                            "unit_price": unit_price,
                            "vat_pct": to_float(item.get("vat_pct"), 0),
                            "line_total": line_total,
                        }
                    )
                if items:
                    return items
        except json.JSONDecodeError:
            pass

    return [
        {
            "description": row.get("description", "Services"),
            "qty": 1.0,
            "unit_price": to_float(row.get("subtotal"), 0),
            "vat_pct": to_float(row.get("vat_rate"), 0),
            "line_total": to_float(row.get("subtotal"), 0),
        }
    ]


def format_money(value, currency):
    return f"{to_float(value):,.2f} {currency}"


def selected_bank_account(settings, invoice_currency):
    accounts = settings.get("bank_accounts") or []
    if not isinstance(accounts, list) or not accounts:
        return {}

    by_currency = [a for a in accounts if (a.get("currency") or "").upper() == invoice_currency.upper()]
    if by_currency:
        for account in by_currency:
            if account.get("default"):
                return account
        return by_currency[0]

    for account in accounts:
        if account.get("default"):
            return account
    return accounts[0]


def draw_pdf(output_path, invoice, settings):
    company = settings.get("company", {})
    invoice_pdf = settings.get("invoice_pdf", {})
    currency = invoice.get("currency") or settings.get("invoice_defaults", {}).get("currency", "RON")
    items = parse_items(invoice)

    logo_path = resolve_path(invoice_pdf.get("logo_path") or company.get("logo_path"))
    if logo_path and not logo_path.exists():
        raise FileNotFoundError(f"Logo file not found: {logo_path}")

    subtotal = to_float(invoice.get("subtotal"), 0)
    vat_amount = to_float(invoice.get("vat_amount"), 0)
    total = to_float(invoice.get("total"), subtotal + vat_amount)

    page_width, page_height = A4
    margin = 36
    line_h = 16
    c = canvas.Canvas(str(output_path), pagesize=A4)
    c.setTitle(f"Invoice {invoice.get('invoice_id', '')}")

    y = page_height - margin
    if logo_path:
        c.drawImage(
            ImageReader(str(logo_path)),
            margin,
            y - 42,
            width=120,
            height=42,
            preserveAspectRatio=True,
            mask="auto",
        )
    c.setFont("Helvetica-Bold", 20)
    c.drawRightString(page_width - margin, y - 4, "INVOICE")
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(page_width - margin, y - 24, invoice.get("invoice_id", ""))
    y -= 58
    c.setStrokeColor(colors.lightgrey)
    c.line(margin, y, page_width - margin, y)
    y -= 22

    left_x = margin
    right_x = page_width / 2 + 18
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left_x, y, "From")
    c.drawString(right_x, y, "Bill To")
    y -= line_h
    c.setFont("Helvetica", 10)
    c.drawString(left_x, y, company.get("name", ""))
    c.drawString(right_x, y, invoice.get("client", ""))
    y -= line_h
    c.drawString(left_x, y, f"CIF: {company.get('cif', '')}")
    c.drawString(right_x, y, f"CIF: {invoice.get('client_cif', '')}")
    y -= line_h

    address = company.get("address", {}) or {}
    company_addr_line = ", ".join(
        p for p in [address.get("street"), address.get("city"), address.get("county"), address.get("country")] if p
    )
    c.drawString(left_x, y, company_addr_line)
    c.drawString(right_x, y, invoice.get("client_address", ""))
    y -= line_h
    c.drawString(left_x, y, company.get("contact", {}).get("email", ""))
    c.drawString(right_x, y, invoice.get("client_email", ""))
    y -= 26

    c.setFont("Helvetica", 10)
    c.drawString(left_x, y, f"Invoice Date: {invoice.get('invoice_date', '')}")
    c.drawString(right_x, y, f"Due Date: {invoice.get('due_date', '')}")
    y -= line_h
    c.drawString(left_x, y, f"Status: {invoice.get('status', '')}")
    c.drawString(right_x, y, f"Currency: {currency}")
    y -= 22

    table_x = margin
    table_w = page_width - margin * 2
    row_h = 18
    col_description = table_x
    col_qty = table_x + table_w * 0.50
    col_unit = table_x + table_w * 0.62
    col_vat = table_x + table_w * 0.78
    col_total = table_x + table_w * 0.89

    c.setFillColor(colors.HexColor("#f2f2f2"))
    c.rect(table_x, y - row_h + 4, table_w, row_h, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(col_description + 4, y - 8, "Description")
    c.drawString(col_qty + 4, y - 8, "Qty")
    c.drawString(col_unit + 4, y - 8, "Unit")
    c.drawString(col_vat + 4, y - 8, "VAT %")
    c.drawString(col_total + 4, y - 8, "Line Total")
    y -= row_h

    c.setFont("Helvetica", 9)
    for item in items:
        c.setStrokeColor(colors.lightgrey)
        c.line(table_x, y - 1, table_x + table_w, y - 1)
        description = (item["description"] or "").strip()
        if len(description) > 48:
            description = f"{description[:45]}..."
        c.drawString(col_description + 4, y - 12, description)
        c.drawRightString(col_unit - 10, y - 12, f"{item['qty']:.2f}")
        c.drawRightString(col_vat - 10, y - 12, format_money(item["unit_price"], currency))
        c.drawRightString(col_total - 10, y - 12, f"{item['vat_pct']:.1f}%")
        c.drawRightString(table_x + table_w - 6, y - 12, format_money(item["line_total"], currency))
        y -= row_h
        if y < 180:
            c.showPage()
            y = page_height - margin
            c.setFont("Helvetica", 9)

    y -= 12
    totals_x = page_width - margin - 180
    c.setFont("Helvetica", 10)
    c.drawString(totals_x, y, "Subtotal:")
    c.drawRightString(page_width - margin, y, format_money(subtotal, currency))
    y -= line_h
    c.drawString(totals_x, y, f"VAT ({to_float(invoice.get('vat_rate'), 0):.1f}%):")
    c.drawRightString(page_width - margin, y, format_money(vat_amount, currency))
    y -= line_h
    c.setFont("Helvetica-Bold", 11)
    c.drawString(totals_x, y, "Total:")
    c.drawRightString(page_width - margin, y, format_money(total, currency))
    y -= 30

    bank = selected_bank_account(settings, currency)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "Payment details")
    c.setFont("Helvetica", 9)
    y -= line_h
    c.drawString(margin, y, f"Method: {invoice.get('payment_method') or 'Bank transfer'}")
    y -= line_h
    c.drawString(margin, y, f"IBAN: {invoice.get('bank_account') or bank.get('iban', '')}")
    y -= line_h
    c.drawString(margin, y, f"Bank: {bank.get('bank_name', '')} ({bank.get('bic', '')})")
    y -= line_h
    c.drawString(margin, y, f"Reference: {invoice.get('invoice_id', '')}")

    c.setFont("Helvetica-Oblique", 8)
    c.drawRightString(
        page_width - margin,
        margin - 8,
        "Generated automatically from company-management ledger",
    )
    c.save()


def sign_pdf_if_enabled(unsigned_pdf, signed_pdf, settings):
    signature_cfg = (settings.get("invoice_pdf") or {}).get("signature") or {}
    if not is_enabled(signature_cfg.get("enabled")):
        if unsigned_pdf != signed_pdf:
            unsigned_pdf.replace(signed_pdf)
        return False

    cert_file = resolve_path(signature_cfg.get("cert_file"))
    key_file = resolve_path(signature_cfg.get("key_file"))
    if not cert_file or not key_file:
        raise ValueError("PDF signature is enabled but cert_file/key_file are not configured.")
    if not cert_file.exists():
        raise FileNotFoundError(f"Certificate file not found: {cert_file}")
    if not key_file.exists():
        raise FileNotFoundError(f"Private key file not found: {key_file}")

    try:
        from pyhanko.sign import signers
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: pyHanko. Install with `pip install pyHanko`."
        ) from exc

    passphrase_env = signature_cfg.get("key_passphrase_env", "INVOICE_PDF_KEY_PASSPHRASE")
    passphrase = os.environ.get(passphrase_env)
    key_passphrase = passphrase.encode("utf-8") if passphrase else None

    signer = signers.SimpleSigner.load(
        key_file=str(key_file),
        cert_file=str(cert_file),
        key_passphrase=key_passphrase,
    )

    metadata = signers.PdfSignatureMetadata(
        field_name=signature_cfg.get("field_name", "Signature1"),
        reason=signature_cfg.get("reason", "Invoice approval"),
        location=signature_cfg.get("location", ""),
    )

    with open(unsigned_pdf, "rb") as infile, open(signed_pdf, "wb") as outfile:
        signers.PdfSigner(signature_meta=metadata, signer=signer).sign_pdf(infile, output=outfile)

    unsigned_pdf.unlink(missing_ok=True)
    return True


def main():
    ensure_ledger()
    args = parse_args()
    settings = load_settings()

    invoice_id = invoice_id_from_context(args.invoice_id)
    invoice = load_invoice(invoice_id)

    output_cfg = (settings.get("invoice_pdf") or {}).get("output_dir", "generated/invoices")
    output_path = Path(args.output) if args.output else Path(output_cfg) / f"{invoice_id}.pdf"
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    unsigned_path = output_path.with_suffix(".unsigned.pdf")
    draw_pdf(unsigned_path, invoice, settings)
    signed = sign_pdf_if_enabled(unsigned_path, output_path, settings)

    suffix = " (signed)" if signed else ""
    print(f"Generated PDF: {output_path}{suffix}")


if __name__ == "__main__":
    main()
