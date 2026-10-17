import json,shutil,hashlib
from pathlib import Path
from datetime import datetime,timezone

R=Path(__file__).resolve().parent
D=R/"data";S=R/"site/data"
S.mkdir(parents=True,exist_ok=True)

latest=json.loads((D/"market_snapshot_latest.json").read_text(encoding="utf-8"))
hist_raw=json.loads((D/"dashboard_history.json").read_text(encoding="utf-8"))
hist=hist_raw.get("records",[]) if isinstance(hist_raw,dict) else hist_raw
watchlist=json.loads((R/"watchlist.json").read_text(encoding="utf-8"))
l2=json.loads((D/"l2_latest.json").read_text(encoding="utf-8")) if (D/"l2_latest.json").exists() else {}
history_status=json.loads((D/"history_status.json").read_text(encoding="utf-8")) if (D/"history_status.json").exists() else {"status":"not_run"}

# Public Pages are market-research only. Never publish account values, share counts,
# transaction rows, cost basis, account history, or account-derived allocation.
public_latest = {
    "_daily_fetch": latest.get("_daily_fetch", {}),
    "market": latest.get("market", {}),
    "funds": latest.get("funds", {}),
}
public_history = []
for row in hist:
    if not isinstance(row, dict):
        continue
    public_row = {
        key: row[key] for key in (
            "run_at", "data_basis_date", "run_type",
            "fund_success_count", "fund_total", "market", "l2", "anomalies",
            "completeness"
        ) if key in row
    }
    # Remove any account-derived anomalies; only allow known market valuation targets.
    targets = set((watchlist.get("targets") or []))
    target_keys = {t.get("key") for t in targets if isinstance(t, dict)}
    if isinstance(public_row.get("anomalies"), list):
        public_row["anomalies"] = [
            a for a in public_row["anomalies"]
            if isinstance(a, dict) and a.get("target") in target_keys
        ]
    public_history.append(public_row)

bundle={
 "schema_version":3,
 "generated_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
 "latest":public_latest,
 "portfolio":{"account_summary":{},"holdings":[],"transactions":[],"public_data":"private_account_data_not_published"},
 "watchlist":watchlist,
 "l2":l2,
 "history_status":history_status
}
(S/"latest.json").write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding="utf-8")
(S/"history.json").write_text(json.dumps({"records":public_history},ensure_ascii=False,indent=2),encoding="utf-8")

manifest=[]
src=D/"history";dst=S/"history";dst.mkdir(parents=True,exist_ok=True)
for p in sorted(src.glob("*.csv")):
    if p.name.startswith("_"):continue
    shutil.copy2(p,dst/p.name)
    points=max(0,len(p.read_text(encoding="utf-8").splitlines())-1)
    manifest.append({"file":p.name,"points":points,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})

(S/"history_manifest.json").write_text(json.dumps({"minimum_formal_l2_points":60,"files":manifest},ensure_ascii=False,indent=2),encoding="utf-8")
(S/"history_status.json").write_text(json.dumps(history_status,ensure_ascii=False,indent=2),encoding="utf-8")
(S/"sync_manifest.json").write_text(json.dumps({"synced_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"files":manifest,"schema_version":3,"account_data_published":False},ensure_ascii=False,indent=2),encoding="utf-8")
