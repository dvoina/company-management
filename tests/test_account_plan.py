import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from account_plan import render_plan_tree, validate_account_plan  # noqa: E402
from ledger_lib import load_account_plan, load_settings  # noqa: E402


class AccountPlanTests(unittest.TestCase):
    def test_repository_account_plan_validates(self):
        errors, warnings = validate_account_plan(load_account_plan(), load_settings())
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_rejects_mapping_to_synthetic_account(self):
        plan = {
            "accounts": [
                {"code": "4", "name": "Root", "kind": "synthetic", "type": "liability", "postable": False},
                {"code": "401", "name": "Furnizori", "parent": "4", "kind": "analytic", "type": "liability", "postable": True},
            ]
        }
        settings = {
            "saft": {"accounts": {"payables": "4"}},
            "expense_categories": {},
        }
        errors, _ = validate_account_plan(plan, settings)
        self.assertTrue(any("must reference an analytic account" in err for err in errors))

    def test_tree_renders_all_accounts(self):
        plan = {
            "accounts": [
                {"code": "4", "name": "Conturi de terți", "kind": "synthetic", "type": "liability", "postable": False},
                {"code": "401", "name": "Furnizori", "parent": "4", "kind": "analytic", "type": "liability", "postable": True},
            ]
        }
        tree = render_plan_tree(plan)
        self.assertIn("4 — Conturi de terți", tree)
        self.assertIn("401 — Furnizori", tree)


if __name__ == "__main__":
    unittest.main()
