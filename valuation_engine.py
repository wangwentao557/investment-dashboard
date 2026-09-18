#!/usr/bin/env python3
import argparse,csv,json,statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def percentile(v,a):
    return sum(x<=v for x in a)/len(a)*100 if a else None

def signal(v,a,th):
    if len(a)<60:
        return "no_data"
    p=percentile(v,a)
    sd=statistics.stdev(a)
    s=(v-statistics.mean(a))/sd if sd else 0
    if p<th["heavy_buy"] and s<th["heavy_buy"]: return "heavy_buy"
    if p<th["buy"] and s<th["buy"]: return "buy"
    if p>th["watch"] and s>th["watch"]: return "high"
    if p>th["hold_high"] and s>th["hold_high"]: return "watch"
    return "hold"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",default="watchlist.json")
    args=ap.parse_args()
    cfg=json.loads(Path(args.config).read_text(encoding="utf-8"))
    targets={}
    formal_ready=True

    for t in cfg["targets"]:
        k=t["key"]
        if t["primary_metric"]=="macro_anchor":
            targets[k]={"signal":"hold","points":0,"required_points":60,"note":"黄金不参与PE/PB/PS估值"}
            continue

        col={"pe_percentile":"pe","pb_percentile":"pb","ps_percentile":"ps"}.get(t["primary_metric"])
        if not col:
            targets[k]={"signal":"no_data","points":0,"required_points":60}
            formal_ready=False
            continue

        p=ROOT/"data/history"/f"{k}.csv"
        vals=[]
        if p.exists():
            with p.open(encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    try: vals.append(float(r[col]))
                    except (TypeError,ValueError): pass

        points=len(vals)
        item={"signal":signal(vals[-1],vals,cfg["signal_thresholds"]["percentile"]) if vals else "no_data","points":points,"required_points":60}
        if points>=60:
            item["percentile"]=round(percentile(vals[-1],vals),2)
            sd=statistics.stdev(vals) if len(vals)>1 else 0
            item["sigma"]=round((vals[-1]-statistics.mean(vals))/sd,2) if sd else 0
        else:
            formal_ready=False
        targets[k]=item

    out={
        "status":"ready" if formal_ready else "no_data",
        "minimum_points":60,
        "targets":targets
    }
    out_path=ROOT/"data/l2_latest.json"
    out_path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False))

if __name__=="__main__":
    main()
