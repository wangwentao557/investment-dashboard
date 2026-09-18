#!/usr/bin/env python3
import argparse,csv,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def percentile(v,a): return sum(x<=v for x in a)/len(a)*100 if a else None
def signal(v,a,th):
    if len(a)<60:return "no_data"
    p=percentile(v,a); sd=statistics.stdev(a); s=(v-statistics.mean(a))/sd if sd else 0
    if p<th["heavy_buy"] and s<th["heavy_buy"]:return "heavy_buy"
    if p<th["buy"] and s<th["buy"]:return "buy"
    if p>th["watch"] and s>th["watch"]:return "high"
    if p>th["hold_high"] and s>th["hold_high"]:return "watch"
    return "hold"
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--config",default="watchlist.json");args=ap.parse_args()
    cfg=json.loads(Path(args.config).read_text(encoding="utf-8")); out={}
    for t in cfg["targets"]:
        k=t["key"]
        if t["primary_metric"]=="macro_anchor":out[k]={"signal":"hold","note":"黄金不参与PE/PB/PS估值"};continue
        col={"pe_percentile":"pe","pb_percentile":"pb","ps_percentile":"ps"}.get(t["primary_metric"])
        if not col:out[k]={"signal":"no_data"};continue
        p=ROOT/"data/history"/f"{k}.csv"; vals=[]
        if p.exists():
            for r in csv.DictReader(p.open(encoding="utf-8-sig")):
                try:vals.append(float(r[col]))
                except:pass
        out[k]={"signal":signal(vals[-1],vals,cfg["signal_thresholds"]["percentile"]) if vals else "no_data","points":len(vals)}
    (ROOT/"data/l2_latest.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False))
if __name__=="__main__":main()
