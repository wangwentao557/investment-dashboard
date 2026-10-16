#!/usr/bin/env python3
"""Fail the public-data pipeline if private account fields enter publishable JSON."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FORBIDDEN = {"portfolio", "account_summary", "transactions", "cash_balance", "cash_history", "total_assets", "total_pnl", "today_pnl", "holdings", "allocation_deviation"}

def main():
    checks = [
        ROOT / "site/data/latest.json",
        ROOT / "site/data/history.json",
        ROOT / "data/dashboard_history.json",
    ]
    failures = []
    for path in checks:
        if not path.exists():
            failures.append(f"missing required public-data file: {path.relative_to(ROOT)}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            failures.append(f"invalid JSON in {path.relative_to(ROOT)}: {type(exc).__name__}")
            continue
        def walk(node, location="$"):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in FORBIDDEN:
                        failures.append(f"forbidden private field {key!r} in {path.relative_to(ROOT)} at {location}")
                    walk(value, location + "." + str(key))
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{location}[{index}]")
        walk(data)
    if failures:
        print("PRIVACY CHECK FAILED")
        for item in failures:
            print("- " + item)
        return 1
    print("PRIVACY CHECK PASSED: public JSON contains no account-level fields.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
