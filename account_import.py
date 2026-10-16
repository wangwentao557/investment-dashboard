#!/usr/bin/env python3
"""Import user-exported account CSVs into local-only storage; never publishes data."""
import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / "account_private"

ALIASES = {
    "transaction_id": ("transaction_id", "transactionid", "流水号", "交易编号", "订单号", "业务流水号"),
    "date": ("date", "交易日期", "确认日期", "发生日期"),
    "action": ("action", "交易类型", "业务类型", "操作"),
    "code": ("code", "基金代码", "产品代码", "证券代码"),
    "name": ("name", "基金名称", "产品名称", "证券名称"),
    "amount": ("amount", "交易金额", "发生金额", "申请金额"),
    "shares": ("shares", "份额", "确认份额", "持有份额"),
    "nav": ("nav", "净值", "成交净值", "单位净值"),
    "fee": ("fee", "手续费", "费用"),
    "status": ("status", "交易状态", "确认状态"),
    "source": ("source", "来源", "渠道"),
    "raw_description": ("raw_description", "备注", "摘要", "交易说明"),
    "as_of": ("as_of", "快照日期", "截止日期", "持仓日期", "日期"),
    "account_id": ("account_id", "账户标识", "账户名称", "账户"),
    "cash_balance": ("cash_balance", "现金余额", "可用余额", "现金"),
    "total_assets": ("total_assets", "总资产", "账户总资产"),
    "unit_cost": ("unit_cost", "持仓成本", "成本净值", "平均成本"),
    "market_value": ("market_value", "市值", "持仓市值", "当前市值"),
    "unrealized_pnl": ("unrealized_pnl", "浮动盈亏", "持仓盈亏", "未实现盈亏"),
}

NUMERIC = {"amount", "shares", "nav", "fee", "cash_balance", "total_assets", "unit_cost", "market_value", "unrealized_pnl"}
TX_REQUIRED = {"date", "action", "code"}
SNAP_REQUIRED = {"as_of", "account_id", "code"}

def normalize_header(value):
    return str(value or "").strip().lower().replace(" ", "").replace("_", "")

def parse_num(value):
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip().replace(",", "").replace("¥", "").replace("￥", "")
    try:
        return float(raw)
    except ValueError:
        return str(value).strip()

def read_rows(path, kind, account_id=None):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV 缺少表头")
        lookup = {}
        for original in reader.fieldnames:
            norm = normalize_header(original)
            for canonical, aliases in ALIASES.items():
                if norm in {normalize_header(a) for a in aliases}:
                    lookup[original] = canonical
                    break
        rows = []
        required = TX_REQUIRED if kind == "transactions" else SNAP_REQUIRED
        for line_no, source_row in enumerate(reader, start=2):
            row = {}
            for key, value in source_row.items():
                canonical = lookup.get(key)
                if canonical:
                    row[canonical] = parse_num(value) if canonical in NUMERIC else (str(value).strip() or None)
            if kind == "snapshots" and not row.get("account_id") and account_id:
                row["account_id"] = account_id
            missing = sorted(k for k in required if row.get(k) in (None, ""))
            if missing:
                raise ValueError(f"第 {line_no} 行缺少必填字段：{', '.join(missing)}")
            if kind == "transactions":
                identity_fields = ("date", "action", "code", "amount", "shares", "nav", "status")
                identity = row.get("transaction_id")
                if not identity:
                    identity = hashlib.sha256(json.dumps([row.get(k) for k in identity_fields], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
                row["_record_id"] = str(identity)
            else:
                row["_record_id"] = "|".join(str(row.get(k, "")) for k in ("as_of", "account_id", "code"))
            row["_source_file"] = Path(path).name
            rows.append(row)
    return rows

def merge_jsonl(path, incoming):
    existing = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                item = json.loads(line)
                existing[str(item.get("_record_id", ""))] = item
    before = len(existing)
    changed = 0
    for item in incoming:
        key = item["_record_id"]
        if existing.get(key) != item:
            changed += 1
        existing[key] = item
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for key in sorted(existing):
            f.write(json.dumps(existing[key], ensure_ascii=False, separators=(",", ":")) + "\n")
    return changed, len(existing)

def main():
    parser = argparse.ArgumentParser(description="将账户导出 CSV 导入本地私有账本")
    parser.add_argument("kind", choices=("transactions", "snapshots"))
    parser.add_argument("csv_file")
    parser.add_argument("--account-id", help="当持仓快照 CSV 没有账户标识列时显式提供")
    args = parser.parse_args()
    try:
        rows = read_rows(args.csv_file, args.kind, args.account_id)
        out = PRIVATE / ("transactions.jsonl" if args.kind == "transactions" else "holdings_snapshots.jsonl")
        added, total = merge_jsonl(out, rows)
        manifest_path = PRIVATE / "import_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"imports": []}
        manifest["imports"].append({
            "kind": args.kind,
            "file_name": Path(args.csv_file).name,
            "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rows_read": len(rows),
            "new_or_updated_records": added,
            "stored_records": total,
            "result": "success",
        })
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "success", "kind": args.kind, "rows_read": len(rows), "new_or_updated_records": added, "stored_records": total, "output": str(out.relative_to(ROOT))}, ensure_ascii=False))
        return 0
    except Exception as exc:
        # Deliberately avoid printing source row contents or account data.
        print(json.dumps({"status": "error", "kind": args.kind, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
