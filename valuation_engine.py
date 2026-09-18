#!/usr/bin/env python3
import argparse,csv,json,statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def percentile(v,a):
    return sum(x<=v for x in a)/len(a)*100 if a else None

def calc(v,a,p_th,s_th):
    if len(a)<60:
        return {"signal":"no_data","points":len(a),"required_points":60}
    p=percentile(v,a)
    sd=statistics.stdev(a) if len(a)>1 else 0
    s=(v-statistics.mean(a))/sd if sd else 0
    if p<p_th["heavy_buy"] and s<s_th["heavy_buy"]:sig="heavy_buy"
    elif p<p_th["buy"] and s<s_th["buy"]:sig="buy"
    elif p>p_th["watch"] and s>s_th["watch"]:sig="high"
    elif p>p_th["hold_high"] and s>s_th["hold_high"]:sig="watch"
    else:sig="hold"
    return {"signal":sig,"points":len(a),"required_points":60,"percentile":round(p,2),"sigma":round(s,2),"mean":round(statistics.mean(a),4),"stdev":round(sd,4)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--config",default="watchlist.json");a=ap.parse_args()
    cfg=json.loads(Path(a.config).read_text(encoding="utf-8"))
    pth=cfg["signal_thresholds"]["percentile"];sth=cfg["signal_thresholds"]["sigma"]
    out_targets={}
    for t in cfg["targets"]:
        key=t["key"]
        if t["primary_metric"]=="macro_anchor":
            out_targets[key]={"signal":"reference_only","points":0,"required_points":60,"note":"黄金只作宏观锚，不参与PE/PB/PS/L2估值"}
            continue
        col={"pe_percentile":"pe","pb_percentile":"pb","ps_percentile":"ps","dividend_spread":"spread","erp":"erp"}.get(t["primary_metric"])
        if not col:
            out_targets[key]={"signal":"no_data","points":0,"required_points":60}
            continue
        path=ROOT/"data/history"/f"{key}.csv";vals=[]
        if path.exists():
            with path.open(encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    try:
                        v=float(r[col])
                        if v==v and abs(v)<1e8:vals.append(v)
                    except (TypeError,ValueError):pass
        item=calc(vals[-1],vals,pth,sth) if vals else {"signal":"no_data","points":0,"required_points":60}
        out_targets[key]=dict(item,metric_column=col,history_window="5y primary; 10y extension if stable")
    non_macro=[k for k,t in [(t["key"],t) for t in cfg["targets"]] if t["primary_metric"]!="macro_anchor"]
    ready=all(out_targets[k].get("points",0)>=60 for k in non_macro)
    out={"schema_version":2,"status":"ready" if ready else "no_data","minimum_points":60,"targets":out_targets}
    (ROOT/"data/l2_latest.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False))

if __name__=="__main__":main()
