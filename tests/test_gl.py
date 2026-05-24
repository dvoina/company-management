import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import gl  # noqa: E402
import ledger_lib  # noqa: E402


class GLTests(unittest.TestCase):
    def setUp(self):
        self.workspace = REPO_ROOT / "tests" / ".gl_workspace"
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.ledger_dir = self.workspace / "ledger"

        self.patches = [
            patch.object(ledger_lib, "LEDGER_DIR", self.ledger_dir),
            patch.object(ledger_lib, "INVOICES_CSV", self.ledger_dir / "invoices.csv"),
            patch.object(ledger_lib, "EXPENSES_CSV", self.ledger_dir / "expenses.csv"),
            patch.object(ledger_lib, "JOURNAL_CSV", self.ledger_dir / "journal.csv"),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

        ledger_lib.ensure_ledger()
        self.addCleanup(self._cleanup_workspace)

    def _cleanup_workspace(self):
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

    def test_income_then_mark_paid_posts_entries(self):
        income_result = gl.add_income(
            client="ACME SRL",
            amount_net=1000.0,
            invoice_date="2026-04-05",
            due_date="2026-05-05",
            description="Consulting",
        )
        self.assertEqual(income_result["invoice_id"], "FCT-001")
        self.assertEqual(income_result["journal_entries"], 3)

        invoices = ledger_lib.read_invoices()
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices[0]["status"], "unpaid")
        self.assertEqual(float(invoices[0]["total"]), 1190.0)
        self.assertEqual(len(ledger_lib.read_journal()), 3)

        paid_result = gl.mark_invoice_paid("FCT-001", paid_date="2026-04-10")
        self.assertEqual(paid_result["status"], "paid")
        self.assertEqual(paid_result["journal_entries"], 2)
        self.assertEqual(len(ledger_lib.read_journal()), 5)
        self.assertEqual(ledger_lib.read_invoices()[0]["paid_date"], "2026-04-10")

    def test_expense_and_summary(self):
        expense_result = gl.add_expense(
            supplier="Vendor SRL",
            amount_net=100.0,
            vat_amount=19.0,
            category="Software",
            expense_date="2026-04-06",
            description="SaaS subscription",
        )
        self.assertEqual(expense_result["expense_id"], "EXP-001")
        self.assertEqual(expense_result["journal_entries"], 3)

        expenses = ledger_lib.read_expenses()
        self.assertEqual(len(expenses), 1)
        self.assertEqual(expenses[0]["gl_account"], "628")
        self.assertEqual(float(expenses[0]["total"]), 119.0)

        summary = gl.build_summary()
        self.assertEqual(summary["invoices"], 0)
        self.assertEqual(summary["expenses"], 1)
        self.assertEqual(summary["total_expenses"], 119.0)
        self.assertEqual(summary["trial_balance_diff"], 0.0)


if __name__ == "__main__":
    unittest.main()
