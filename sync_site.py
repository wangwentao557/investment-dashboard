import json,shutil,hashlib
from pathlib import Path
from datetime import datetime,timezone

R=Path(__file__).resolve().parent
D=R/"data";S=R/"site/data"
S.mkdir(parents=True,exist_ok=True)

latest=json.loads((D/"market_snapshot_latest.json").read_text(encoding="utf-8"))
hist_raw=json.loads((D/"dashboard_history.json").read_text(encoding="utf-8"))
hist=hist_raw.get("records",[]) if isinstance(hist_raw,dict) else hist_raw
# Public history must never contain account-level holdings, cash, P/L, or transactions.
public_fields=("run_at","data_basis_date","fund_success_count","fund_total","market","l2","anomalies","completeness")
hist=[{k:r[k] for k in public_fields if k in r} for r in hist if isinstance(r,dict)]
watchlist=json.loads((R/"watchlist.json").read_text(encoding="utf-8"))
l2=json.loads((D/"l2_latest.json").read_text(encoding="utf-8")) if (D/"l2_latest.json").exists() else {}
history_status=json.loads((D/"history_status.json").read_text(encoding="utf-8")) if (D/"history_status.json").exists() else {"status":"not_run"}

bundle={
 "schema_version":2,
 "generated_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
 "latest":latest,
 "watchlist":watchlist,
 "l2":l2,
 "history_status":history_status
}
(S/"latest.json").write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding="utf-8")
(S/"history.json").write_text(json.dumps({"records":hist},ensure_ascii=False,indent=2),encoding="utf-8")

manifest=[]
src=D/"history";dst=S/"history";dst.mkdir(parents=True,exist_ok=True)
for p in sorted(src.glob("*.csv")):
    if p.name.startswith("_"):continue
    shutil.copy2(p,dst/p.name)
    points=max(0,len(p.read_text(encoding="utf-8").splitlines())-1)
    manifest.append({"file":p.name,"points":points,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})

(S/"history_manifest.json").write_text(json.dumps({"minimum_formal_l2_points":60,"files":manifest},ensure_ascii=False,indent=2),encoding="utf-8")
(S/"history_status.json").write_text(json.dumps(history_status,ensure_ascii=False,indent=2),encoding="utf-8")
(S/"sync_manifest.json").write_text(json.dumps({"synced_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"files":manifest,"schema_version":2},ensure_ascii=False,indent=2),encoding="utf-8")
