import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "account_import.py"
spec = importlib.util.spec_from_file_location("account_import", MODULE_PATH)
account_import = importlib.util.module_from_spec(spec)
spec.loader.exec_module(account_import)

class AccountImportTests(unittest.TestCase):
    def write_csv(self, path, headers, rows):
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

    def test_transaction_import_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "tx.csv"
            target = Path(tmp) / "transactions.jsonl"
            self.write_csv(source, ["transaction_id", "date", "action", "code", "amount"],
                           [{"transaction_id": "T-1", "date": "2026-10-01", "action": "buy", "code": "000001", "amount": "100.00"}])
            rows = account_import.read_rows(source, "transactions")
            changed, total = account_import.merge_jsonl(target, rows)
            self.assertEqual((changed, total), (1, 1))
            rows = account_import.read_rows(source, "transactions")
            changed, total = account_import.merge_jsonl(target, rows)
            self.assertEqual((changed, total), (0, 1))
            stored = [json.loads(x) for x in target.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(stored[0]["amount"], 100.0)

    def test_snapshot_requires_account_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "snapshot.csv"
            self.write_csv(source, ["as_of", "code", "shares"],
                           [{"as_of": "2026-10-01", "code": "000001", "shares": "10"}])
            with self.assertRaisesRegex(ValueError, "account_id"):
                account_import.read_rows(source, "snapshots")
            rows = account_import.read_rows(source, "snapshots", account_id="default-account")
            self.assertEqual(rows[0]["account_id"], "default-account")

    def test_missing_required_transaction_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bad.csv"
            self.write_csv(source, ["date", "action"], [{"date": "2026-10-01", "action": "buy"}])
            with self.assertRaisesRegex(ValueError, "code"):
                account_import.read_rows(source, "transactions")

if __name__ == "__main__":
    unittest.main()
