#!/usr/bin/env python3
"""Import user-exported transaction and holdings snapshot files into a local private ledger.

No network access, credentials, browser scraping, or invented account data.
Supported input: CSV or JSON exports. Original rows are retained alongside normalized fields.
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
    "date": ("date", "交易日期", "确认日期", "时间", "日期"),
    "transaction_id": ("transaction_id", "交易单号", "订单号", "流水号", "业务编号"),
    "action": ("action", "交易类型", "业务类型", "操作"),
    "fund_code": ("fund_code", "基金代码", "产品代码", "代码"),
    "fund_name": ("fund_name", "基金名称", "产品名称", "产品"),
    "amount": ("amount", "交易金额", "金额", "发生金额"),
    "shares": ("shares", "确认份额", "交易份额", "份额"),
    "nav": ("nav", "确认净值", "成交净值", "单位净值"),
    "fee": ("fee", "手续费", "费用"),
    "status": ("status", "交易状态", "确认状态", "状态"),
    "cash_balance": ("cash_balance", "现金余额", "可用余额", "账户余额"),
    "market_value": ("market_value", "持仓市值", "市值", "金额"),
    "cost_basis": ("cost_basis", "持仓成本", "成本金额", "成本"),
    "snapshot_at": ("snapshot_at", "快照时间", "统计日期", "日期", "date"),
}

def _read(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return [dict(row) for row in csv.DictReader(f)]
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("records", "transactions", "holdings", "data", "items"):
                if isinstance(data.get(key), list):
                    return [x for x in data[key] if isinstance(x, dict)]
        raise ValueError(f"{path}: JSON must be a list or contain a records/data/items list")
    raise ValueError(f"Unsupported file type: {path.suffix}; use CSV or JSON")

def _normalize(row: dict[str, Any], kind: str) -> dict[str, Any]:
    aliases = dict(ALIASES)
    if kind == "snapshot":
        aliases.pop("transaction_id", None)
        aliases.pop("action", None)
    out: dict[str, Any] = {}
    for field, names in aliases.items():
        for name in names:
            if name in row and row[name] not in (None, ""):
                out[field] = str(row[name]).strip()
                break
    out["record_type"] = kind
    out["source_row"] = row
    return out

def _key(record: dict[str, Any], kind: str) -> str:
    if kind == "transaction" and record.get("transaction_id"):
        identity = [kind, record["transaction_id"]]
    elif kind == "transaction":
        identity = [kind] + [record.get(k, "") for k in ("date", "fund_code", "action", "amount", "shares", "nav", "status")]
    else:
        identity = [kind] + [record.get(k, "") for k in ("snapshot_at", "fund_code", "shares", "market_value", "cost_basis", "cash_balance")]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

def import_file(source: Path, kind: str, private_dir: Path) -> dict[str, Any]:
    if kind not in ("transaction", "snapshot"):
        raise ValueError("kind must be transaction or snapshot")
    rows = _read(source)
    normalized = [_normalize(row, kind) for row in rows]
    required = ("date", "fund_code") if kind == "transaction" else ("snapshot_at", "fund_code")
    invalid = [i for i, r in enumerate(normalized, 1) if any(not r.get(k) for k in required)]
    if invalid:
        raise ValueError(f"Missing required fields on input rows: {invalid[:20]}")
    private_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(private_dir, 0o700)
    dest = private_dir / ("transactions.jsonl" if kind == "transaction" else "holdings_snapshots.jsonl")
    existing: dict[str, dict[str, Any]] = {}
    if dest.exists():
        for line in dest.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                existing[r["_dedupe_key"]] = r
    added = 0
    for r in normalized:
        k = _key(r, kind)
        if k in existing:
            continue
        r["_dedupe_key"] = k
        r["imported_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        r["source_file_name"] = source.name
        existing[k] = r
        added += 1
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in existing.values()), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(dest)
    manifest_path = private_dir / "import_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"imports": []}
    manifest["imports"].append({
        "source_file_name": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "kind": kind,
        "rows_read": len(rows),
        "rows_added": added,
        "rows_duplicate": len(rows) - added,
        "destination": dest.name,
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(manifest_path, 0o600)
    return {"kind": kind, "rows_read": len(rows), "rows_added": added, "rows_duplicate": len(rows) - added, "destination": str(dest)}

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--transactions", type=Path, help="CSV/JSON transaction export")
    ap.add_argument("--snapshot", type=Path, help="CSV/JSON holdings snapshot export")
    ap.add_argument("--private-dir", type=Path, default=Path("private_account"), help="Local private storage directory (gitignored)")
    args = ap.parse_args()
    if not args.transactions and not args.snapshot:
        ap.error("provide --transactions and/or --snapshot")
    for source, kind in ((args.transactions, "transaction"), (args.snapshot, "snapshot")):
        if source:
            result = import_file(source, kind, args.private_dir)
            print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
