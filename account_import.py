#!/usr/bin/env python3
"""Import exported account CSV/JSON files into a local private ledger.

This module does not connect to Tencent Licaitong, perform login, scrape pages,
or invent missing fields. The default destination is outside the repository.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALIASES = {
    "transaction_id": ("transaction_id", "transactionId", "订单号", "交易流水号", "流水号", "交易单号"),
    "date": ("date", "交易时间", "发生时间", "日期", "申请时间", "确认时间"),
    "code": ("code", "基金代码", "产品代码", "证券代码"),
    "name": ("name", "基金名称", "产品名称", "证券名称"),
    "action": ("action", "交易类型", "业务类型", "操作"),
    "amount": ("amount", "交易金额", "发生金额", "金额", "申请金额"),
    "shares": ("shares", "确认份额", "持有份额", "基金份额", "份额"),
    "nav": ("nav", "确认净值", "单位净值", "成交净值"),
    "fee": ("fee", "手续费", "费用", "申购费"),
    "status": ("status", "交易状态", "确认状态", "状态"),
    "snapshot_date": ("snapshot_date", "快照日期", "统计日期", "日期", "date"),
    "holding_value": ("holding_value", "持仓市值", "市值", "资产金额"),
    "cost_basis": ("cost_basis", "持仓成本", "成本金额"),
    "cash_balance": ("cash_balance", "现金余额", "可用余额", "现金"),
    "total_assets": ("total_assets", "总资产", "账户总资产", "资产总额"),
}
TRANSACTION_FIELDS = ("transaction_id", "date", "code", "name", "action", "amount", "shares", "nav", "fee", "status")
SNAPSHOT_FIELDS = ("snapshot_date", "code", "name", "shares", "nav", "holding_value", "cost_basis", "cash_balance", "total_assets")


def _first(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for key in aliases:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def normalize(row: dict[str, Any], kind: str, source_name: str) -> dict[str, Any]:
    fields = TRANSACTION_FIELDS if kind == "transactions" else SNAPSHOT_FIELDS
    result = {field: _first(row, ALIASES[field]) for field in fields}
    result["source_file"] = source_name
    result["imported_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result["raw"] = row
    if kind == "transactions" and not result.get("date"):
        raise ValueError("transaction row is missing a transaction date")
    if kind == "snapshots" and not result.get("snapshot_date"):
        raise ValueError("holding snapshot row is missing a snapshot date")
    if kind == "transactions" and not result.get("transaction_id"):
        stable = {k: result.get(k) for k in TRANSACTION_FIELDS if k != "transaction_id"}
        result["dedupe_key"] = hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    else:
        key_fields = TRANSACTION_FIELDS if kind == "transactions" else SNAPSHOT_FIELDS
        stable = {k: result.get(k) for k in key_fields}
        result["dedupe_key"] = str(result.get("transaction_id") or hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest())
    return result


def read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return [dict(row) for row in csv.DictReader(stream)]
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("records") or data.get("transactions") or data.get("holdings") or data.get("data")
            if rows is None:
                rows = [data]
        else:
            raise ValueError("JSON input must be an object or list")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("input records must be a list of objects")
        return rows
    raise ValueError("Only CSV and JSON exports are supported")


def import_file(source: Path, kind: str, out_dir: Path) -> dict[str, Any]:
    if kind not in {"transactions", "snapshots"}:
        raise ValueError("kind must be transactions or snapshots")
    rows = read_rows(source)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{kind}.jsonl"
    existing: set[str] = set()
    if target.exists():
        with target.open("r", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    existing.add(json.loads(line)["dedupe_key"])
    added = duplicates = rejected = 0
    errors: list[dict[str, Any]] = []
    with target.open("a", encoding="utf-8") as stream:
        for index, row in enumerate(rows, start=2):
            try:
                item = normalize(row, kind, source.name)
                if item["dedupe_key"] in existing:
                    duplicates += 1
                    continue
                stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
                existing.add(item["dedupe_key"])
                added += 1
            except (ValueError, TypeError) as exc:
                rejected += 1
                errors.append({"row": index, "reason": str(exc)})
    report = {
        "kind": kind, "source_file": source.name, "input_rows": len(rows),
        "added": added, "duplicates": duplicates, "rejected": rejected,
        "errors": errors, "output_file": str(target),
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Contains personal financial data. Keep outside public repositories and website directories."
    }
    (out_dir / f"import_report_{kind}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", choices=("transactions", "snapshots"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path(os.environ.get("PRIVATE_ACCOUNT_DIR", str(Path.home() / ".investment-dashboard-private"))))
    args = parser.parse_args()
    report = import_file(args.input, args.type, args.out_dir)
    print(json.dumps({k: v for k, v in report.items() if k not in {"errors", "output_file"}}, ensure_ascii=False, indent=2))
    if report["rejected"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
