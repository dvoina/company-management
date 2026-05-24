#!/usr/bin/env python3
"""Validate and visualize the chart of accounts."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ledger_lib import account_plan_index, load_account_plan, load_settings

VALID_ACCOUNT_TYPES = {"asset", "liability", "equity", "revenue", "expense", "off_balance"}
VALID_KINDS = {"synthetic", "analytic"}


def _code(value):
    return str(value or "").strip()


def _bool(value, default=True):
    if value is None:
        return default
    return bool(value)


def validate_account_plan(plan, settings):
    errors = []
    warnings = []

    accounts = plan.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        return ["account_plan.yml must define a non-empty 'accounts' list"], warnings

    index = {}
    children = defaultdict(list)

    for pos, row in enumerate(accounts, 1):
        if not isinstance(row, dict):
            errors.append(f"accounts[{pos}] must be an object")
            continue

        code = _code(row.get("code"))
        name = str(row.get("name") or "").strip()
        kind = str(row.get("kind") or "").strip()
        account_type = str(row.get("type") or "").strip()
        parent = _code(row.get("parent"))

        if not code.isdigit():
            errors.append(f"accounts[{pos}] has invalid code '{code}' (must be digits)")
            continue
        if code in index:
            errors.append(f"duplicate account code '{code}'")
            continue
        if not name:
            errors.append(f"account '{code}' is missing 'name'")
        if kind not in VALID_KINDS:
            errors.append(f"account '{code}' has invalid kind '{kind}' (expected synthetic|analytic)")
        if account_type not in VALID_ACCOUNT_TYPES:
            errors.append(
                f"account '{code}' has invalid type '{account_type}' "
                f"(expected one of {sorted(VALID_ACCOUNT_TYPES)})"
            )

        index[code] = row

        if parent:
            children[parent].append(code)

    for code, row in index.items():
        parent = _code(row.get("parent"))
        if not parent:
            continue
        if parent not in index:
            errors.append(f"account '{code}' references missing parent '{parent}'")
            continue
        if code == parent or not code.startswith(parent):
            errors.append(f"account '{code}' must extend parent code '{parent}' by prefix")

    for code, row in index.items():
        kind = str(row.get("kind") or "")
        has_children = bool(children.get(code))
        postable = _bool(row.get("postable"), default=(kind == "analytic"))

        if kind == "analytic" and has_children:
            errors.append(f"analytic account '{code}' cannot have children")
        if kind == "synthetic" and postable:
            errors.append(f"synthetic account '{code}' cannot be postable")

    settings_codes = {}
    for key, value in (settings.get("saft", {}).get("accounts", {}) or {}).items():
        settings_codes[f"saft.accounts.{key}"] = _code(value)
    for cat, cfg in (settings.get("expense_categories", {}) or {}).items():
        settings_codes[f"expense_categories.{cat}.account"] = _code((cfg or {}).get("account"))

    for label, code in settings_codes.items():
        if not code:
            errors.append(f"{label} is empty")
            continue
        account = index.get(code)
        if not account:
            errors.append(f"{label} references unknown account '{code}'")
            continue
        if str(account.get("kind") or "") != "analytic":
            errors.append(f"{label} must reference an analytic account, got '{code}'")
        if not _bool(account.get("postable"), default=True):
            errors.append(f"{label} references non-postable account '{code}'")

    return errors, warnings


def _children_map(index):
    children = defaultdict(list)
    for code, row in index.items():
        parent = _code(row.get("parent"))
        if parent and parent in index:
            children[parent].append(code)
    for code in children:
        children[code].sort(key=lambda c: (len(c), c))
    return children


def _roots(index):
    out = []
    for code, row in index.items():
        parent = _code(row.get("parent"))
        if not parent or parent not in index:
            out.append(code)
    out.sort(key=lambda c: (len(c), c))
    return out


def render_plan_tree(plan, markdown=False):
    index = account_plan_index(plan)
    children = _children_map(index)
    roots = _roots(index)

    lines = []
    if markdown:
        lines.append("# Chart of Accounts")
        lines.append("")

    def walk(code, depth):
        row = index[code]
        marker = "A" if str(row.get("kind")) == "analytic" else "S"
        postable = "P" if _bool(row.get("postable"), default=(marker == "A")) else "NP"
        prefix = "  " * depth + ("- " if markdown else "• ")
        lines.append(f"{prefix}{code} — {row.get('name','')} [{marker}/{postable}]")
        for child in children.get(code, []):
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)

    return "\n".join(lines).strip() + "\n"


def cli():
    parser = argparse.ArgumentParser(description="Chart of accounts validator/visualizer")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="Validate ledger/account_plan.yml and related settings mappings")

    tree_p = sub.add_parser("tree", help="Render the chart of accounts tree")
    tree_p.add_argument("--markdown", action="store_true", help="Render as markdown")
    tree_p.add_argument("--output", help="Write rendered tree to a file")

    args = parser.parse_args()
    plan = load_account_plan()
    settings = load_settings()

    if args.command == "validate":
        errors, warnings = validate_account_plan(plan, settings)
        if warnings:
            print("⚠️  Warnings:")
            for warning in warnings:
                print(f"  - {warning}")
        if errors:
            print("❌ Account plan validation failed:")
            for error in errors:
                print(f"  - {error}")
            raise SystemExit(1)
        print(f"✅ Account plan valid — {len(account_plan_index(plan))} accounts")
        return

    rendered = render_plan_tree(plan, markdown=args.markdown)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
        print(f"Chart of accounts written to {out}")
        return
    print(rendered, end="")


if __name__ == "__main__":
    cli()
