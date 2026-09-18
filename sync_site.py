import json,shutil,hashlib
from pathlib import Path
from datetime import datetime,timezone
R=Path(__file__).resolve().parent;D=R/'data';S=R/'site/data';S.mkdir(parents=True,exist_ok=True)
latest=json.loads((D/'market_snapshot_latest.json').read_text()); hist=json.loads((D/'dashboard_history.json').read_text())
bundle={'schema_version':1,'generated_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'latest':latest,'portfolio':json.loads((R/'portfolio.json').read_text()),'watchlist':json.loads((R/'watchlist.json').read_text()),'l2':json.loads((D/'l2_latest.json').read_text()) if (D/'l2_latest.json').exists() else {}}
(S/'latest.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2));(S/'history.json').write_text(json.dumps({'records':hist},ensure_ascii=False,indent=2))
manifest=[]
for p in (D/'history').glob('*.csv'):
 if p.name.startswith('_'):continue
 (S/'history').mkdir(parents=True,exist_ok=True);shutil.copy2(p,S/'history'/p.name)
 manifest.append({'file':p.name,'points':max(0,len(p.read_text().splitlines())-1),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(S/'history_manifest.json').write_text(json.dumps({'minimum_formal_l2_points':60,'files':manifest},ensure_ascii=False,indent=2));(S/'sync_manifest.json').write_text(json.dumps({'synced_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'files':manifest},ensure_ascii=False,indent=2))
