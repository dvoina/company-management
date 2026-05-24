# 🏢 GitHub as a Company OS

A minimal, git-native back-office for solo operators and tiny teams.
Issues are documents. Actions are automation. The wiki is your dashboard.

---

## Country Scope (Important)

This starter is **Romania-centered** out of the box (language, assumptions, and default VAT-oriented bookkeeping flow are tuned for Romanian solo operations).

To adapt it for another country (for example, **Estonia**), update these parts first:
1. `README.md` and issue templates (`.github/ISSUE_TEMPLATE/*`) to match local terms and required invoice fields.
2. Validation/reporting rules in `scripts/validate_ledger.py` and `scripts/monthly_report.py` for local tax/VAT logic.
3. Default categories, currency, and invoice metadata in the templates and ledger conventions (for Estonia, typically EUR and local VAT handling).

---

## Setup

1. **Create a private repo** and push this directory.
2. **Enable wiki** in repo settings (Issues → Wiki).
3. **Allow Actions to write** to the repo:
   - Settings → Actions → General → Workflow permissions → *Read and write*
4. That's it. No secrets needed for core functionality.
5. For local script runs, install dependencies with `pip install -r requirements.txt`.
6. For local accounting actions, use `python gl.py --help`.

Run tests locally:
```
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## Local CLI (gl.py)

`gl.py` provides non-interactive local commands that write to the same ledger files used by CI workflows.

Examples:
```bash
python gl.py income --client "ACME SRL" --amount-net 1000 --date 2026-04-05 --due-date 2026-05-05 --json
python gl.py expense --supplier "Vendor SRL" --amount-net 100 --vat-amount 19 --category Software --date 2026-04-06 --json
python gl.py pay --invoice-id FCT-001 --paid-date 2026-04-10 --json
python gl.py summary --json
python gl.py validate
```

---

## How It Works

### Creating an Invoice

1. Open a new issue using the **Invoice** template.
2. Fill in the fields — client, line items, totals, due date.
3. Submit. The Action fires, assigns an `INV-XXX` ID, and appends it to `ledger/invoices.csv`.
4. A branded PDF is generated at:

```
generated/invoices/INV-XXX.pdf
```

**When paid:**
Add the label `paid` to the issue. The Action records the payment date and closes the issue.

### Invoice PDF Branding & Signing

Invoice PDFs are rendered by `scripts/generate_invoice_pdf.py` using data from `ledger/invoices.csv`.

1. Put your logo file in the repo (for example `assets/logo.png`) and set `invoice_pdf.logo_path` in `settings.yml`.
2. (Optional) Enable certificate signing in `settings.yml` under `invoice_pdf.signature`.
3. If your private key is encrypted, set `INVOICE_PDF_KEY_PASSPHRASE` as a repository secret.

Dependencies are managed via `requirements.txt`; the invoice workflow installs from it, generates the PDF, and applies a digital signature when enabled.

---

### Logging an Expense

1. Open a new issue using the **Expense** template.
2. Fill in date, amount, category, vendor.
3. Submit. The Action logs it to `ledger/expenses.csv` and auto-closes the issue.

**Categories:** Software · Travel · Hardware · Office · Marketing · Other

---

### Monthly Reports

On the 1st of every month, two documents for the previous month are auto-generated at:

```
generated/reports/YYYY-MM.md
generated/reports/YYYY-MM-balance-sheet.md
```

And pushed to the wiki at:
- `Report-YYYY-MM`
- `Balance-Sheet-YYYY-MM`

**Trigger manually** any time via Actions → Monthly Report → Run workflow.
Pass a specific `YYYY-MM` to generate a report for any past month.

---

### Ledger Validation

Every push to `ledger/` runs a validation check:
- Duplicate IDs
- Negative amounts
- VAT math consistency
- Overdue invoices still marked unpaid

Failures block merges if you set branch protection rules.

---

## Ledger Schema

**invoices.csv**
| Field | Description |
|---|---|
| invoice_id | INV-001, INV-002, … |
| issue_number | GitHub issue # |
| client | Client name |
| client_email | Client email |
| invoice_date | YYYY-MM-DD |
| due_date | YYYY-MM-DD |
| currency | EUR, USD, etc. |
| subtotal | Before VAT |
| vat_rate | e.g. 19.0 |
| vat_amount | Computed VAT |
| total | Final amount |
| status | unpaid / paid / overdue / cancelled |
| paid_date | YYYY-MM-DD when paid |
| description | First line item |

**expenses.csv**
| Field | Description |
|---|---|
| expense_id | EXP-001, EXP-002, … |
| issue_number | GitHub issue # |
| date | YYYY-MM-DD |
| amount | Amount paid |
| currency | EUR, USD, etc. |
| category | Software / Travel / etc. |
| vendor | Who you paid |
| description | What for |
| tax_deductible | Yes / No / Partial |

---

## Tips

- **Scenario planning:** Create a branch, edit the CSVs manually, run `monthly_report.py` locally to see the P&L impact. Discard the branch when done.
- **Balance sheet preview:** Run `python scripts/balance_sheet.py` (optionally with `REPORT_MONTH=YYYY-MM`) to inspect end-of-month assets, liabilities, and equity.
- **Year-end:** Tag the last commit of December as `fiscal-YYYY`. Immutable audit point.
- **Overdue chasing:** Filter open issues with label `invoice` + `unpaid` for your AR view.
- **git log is your audit trail:** every ledger change is a commit. Nothing is lost.

---

## File Structure

```
.github/
  workflows/
    invoice.yml          # Invoice lifecycle automation
    expense.yml          # Expense logging automation
    monthly_report.yml   # Scheduled P&L reports
    validate_ledger.yml  # Integrity checks on every push
  ISSUE_TEMPLATE/
    invoice.md           # Invoice issue template
    expense.md           # Expense issue template
ledger/
  invoices.csv           # All invoices
  expenses.csv           # All expenses
scripts/
  ledger_lib.py          # Shared utilities
  register_invoice.py    # Parse & register invoice issues
  generate_invoice_pdf.py# Render invoice PDFs (+ optional signing)
  mark_paid.py           # Mark invoice paid
  log_expense.py         # Parse & log expense issues
  monthly_report.py      # Generate P&L markdown
  balance_sheet.py       # Generate month-end balance sheet markdown
  validate_ledger.py     # Integrity validation
  push_to_wiki.py        # Push reports to wiki
generated/
  reports/               # YYYY-MM.md report files
```

---

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.
See the [LICENSE](./LICENSE) file for the full license text.
