import csv
import json
import tempfile
import unittest
from pathlib import Path

from account_import import import_file


class AccountImportTests(unittest.TestCase):
    def test_transaction_import_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "transactions.csv"
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["交易流水号", "交易时间", "基金代码", "交易类型", "交易金额", "确认份额"])
                writer.writeheader()
                writer.writerow({"交易流水号": "T-001", "交易时间": "2026-10-16", "基金代码": "000001", "交易类型": "申购", "交易金额": "100", "确认份额": "98.5"})
            first = import_file(source, "transactions", root / "private")
            second = import_file(source, "transactions", root / "private")
            self.assertEqual(first["added"], 1)
            self.assertEqual(second["added"], 0)
            self.assertEqual(second["duplicates"], 1)
            stored = (root / "private" / "transactions.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(stored), 1)
            self.assertEqual(json.loads(stored[0])["transaction_id"], "T-001")

    def test_snapshot_import_rejects_missing_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "snapshot.json"
            source.write_text(json.dumps({"holdings": [{"基金代码": "000001", "持仓市值": "100"}]}, ensure_ascii=False), encoding="utf-8")
            report = import_file(source, "snapshots", root / "private")
            self.assertEqual(report["added"], 0)
            self.assertEqual(report["rejected"], 1)


if __name__ == "__main__":
    unittest.main()
