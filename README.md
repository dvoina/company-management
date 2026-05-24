# 🏢 GitHub as a Company OS

A minimal, git-native back-office for solo operators and tiny teams.
Issues are documents. Actions are automation. The wiki is your dashboard.

---

## Setup

1. **Create a private repo** and push this directory.
2. **Enable wiki** in repo settings (Issues → Wiki).
3. **Allow Actions to write** to the repo:
   - Settings → Actions → General → Workflow permissions → *Read and write*
4. That's it. No secrets needed for core functionality.

---

## How It Works

### Creating an Invoice

1. Open a new issue using the **Invoice** template.
2. Fill in the fields — client, line items, totals, due date.
3. Submit. The Action fires, assigns an `INV-XXX` ID, and appends it to `ledger/invoices.csv`.

**When paid:**
Add the label `paid` to the issue. The Action records the payment date and closes the issue.

---

### Logging an Expense

1. Open a new issue using the **Expense** template.
2. Fill in date, amount, category, vendor.
3. Submit. The Action logs it to `ledger/expenses.csv` and auto-closes the issue.

**Categories:** Software · Travel · Hardware · Office · Marketing · Other

---

### Monthly Reports

On the 1st of every month, a report for the previous month is auto-generated at:

```
generated/reports/YYYY-MM.md
```

And pushed to the wiki at `Report-YYYY-MM`.

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
  mark_paid.py           # Mark invoice paid
  log_expense.py         # Parse & log expense issues
  monthly_report.py      # Generate P&L markdown
  validate_ledger.py     # Integrity validation
  push_to_wiki.py        # Push reports to wiki
generated/
  reports/               # YYYY-MM.md report files
```
