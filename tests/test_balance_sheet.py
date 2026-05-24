import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import balance_sheet  # noqa: E402


def sample_settings():
    return {
        "invoice_defaults": {"currency": "RON"},
        "saft": {
            "accounts": {
                "receivables": "4111",
                "payables": "401",
                "vat_collected": "4427",
                "vat_deductible": "4426",
                "vat_payable": "4423",
                "cash": "5311",
                "bank_ron": "5121",
                "bank_eur": "5124",
            }
        },
        "balance_sheet": {
            "account_prefixes": {"assets": [], "liabilities": [], "equity": []}
        },
    }


class BalanceSheetTests(unittest.TestCase):
    def test_month_end_date_handles_leap_year(self):
        self.assertEqual(balance_sheet.month_end_date("2024-02"), "2024-02-29")

    def test_classify_account_uses_custom_prefix_before_defaults(self):
        settings = sample_settings()
        account_prefixes = {
            "assets": [],
            "liabilities": [],
            "equity": ["411"],
        }
        self.assertEqual(
            balance_sheet.classify_account("4111", account_prefixes, settings), "equity"
        )

    def test_main_generates_balanced_report_with_current_result(self):
        journal_rows = [
            {
                "date": "2026-04-05",
                "account_code": "4111",
                "account_name": "Clients",
                "debit": "1190",
                "credit": "0",
            },
            {
                "date": "2026-04-05",
                "account_code": "704",
                "account_name": "Revenue",
                "debit": "0",
                "credit": "1000",
            },
            {
                "date": "2026-04-05",
                "account_code": "4427",
                "account_name": "VAT collected",
                "debit": "0",
                "credit": "190",
            },
            {
                "date": "2026-04-10",
                "account_code": "5121",
                "account_name": "Bank RON",
                "debit": "1190",
                "credit": "0",
            },
            {
                "date": "2026-04-10",
                "account_code": "4111",
                "account_name": "Clients",
                "debit": "0",
                "credit": "1190",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            with (
                patch.object(balance_sheet, "REPORTS_DIR", reports_dir),
                patch.object(balance_sheet, "get_target_month", return_value="2026-04"),
                patch.object(balance_sheet, "load_settings", return_value=sample_settings()),
                patch.object(balance_sheet, "read_journal", return_value=journal_rows),
            ):
                balance_sheet.main()

            out_path = reports_dir / "2026-04-balance-sheet.md"
            self.assertTrue(out_path.exists())
            content = out_path.read_text()
            self.assertIn("### Assets", content)
            self.assertIn("### Liabilities", content)
            self.assertIn("### Equity", content)
            self.assertIn("| 5121 | Bank RON | 1,190.00 RON |", content)
            self.assertIn("| 4427 | VAT collected | 190.00 RON |", content)
            self.assertIn("| P&L | Current year result | 1,000.00 RON |", content)
            self.assertIn("| **Imbalance** | **0.00 RON** |", content)

    def test_main_lists_unclassified_accounts(self):
        journal_rows = [
            {
                "date": "2026-04-15",
                "account_code": "8888",
                "account_name": "Unknown",
                "debit": "50",
                "credit": "0",
            }
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            with (
                patch.object(balance_sheet, "REPORTS_DIR", reports_dir),
                patch.object(balance_sheet, "get_target_month", return_value="2026-04"),
                patch.object(balance_sheet, "load_settings", return_value=sample_settings()),
                patch.object(balance_sheet, "read_journal", return_value=journal_rows),
            ):
                balance_sheet.main()

            content = (reports_dir / "2026-04-balance-sheet.md").read_text()
            self.assertIn("### Unclassified accounts", content)
            self.assertIn("| 8888 | Unknown (debit) | 50.00 RON |", content)


if __name__ == "__main__":
    unittest.main()
