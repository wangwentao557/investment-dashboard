#!/usr/bin/env python3
import argparse,csv,json,time
from pathlib import Path
from datetime import datetime,timedelta,timezone
from lixinger_api import fundamental,national_debt,years_ago,token

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"; HIST=DATA/"history"; TZ=timezone(timedelta(hours=8))
TARGETS={
"div_lowvol":{"market":"cn","code":"H30269","api_metric":"dyr.mcw","extra":"cn10y"},
"hs300":{"market":"cn","code":"000300","api_metric":"pe_ttm.mcw"},
"csi_a50":{"market":"cn","code":"930050","api_metric":"pe_ttm.mcw"},
"cs_ai":{"market":"cn","code":"930713","api_metric":"ps_ttm.mcw"},
"hk_internet":{"market":"cn","code":"931637","api_metric":"ps_ttm.mcw"},
"metals":{"market":"cn","code":"000819","api_metric":"pb.mcw"},
"ndx":{"market":"us","code":".NDX","api_metric":"pe_ttm.mcw","extra":"us10y"},
"spx":{"market":"us","code":".INX","api_metric":"pe_ttm.mcw","extra":"us10y"},
}
FIELDS=["date","pe","pb","ps","dividend_yield","cn10y","spread","us10y","erp"]

def write_csv(key,rows):
    p=HIST/f"{key}.csv"; p.parent.mkdir(parents=True,exist_ok=True); old={}
    if p.exists():
        with p.open(encoding="utf-8-sig",newline="") as f:
            for r in csv.DictReader(f):
                if r.get("date"): old[r["date"]]=r
    for r in rows:
        if r.get("date"): old[r["date"]]=r
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader()
        for d in sorted(old):
            w.writerow({k:old[d].get(k,"") for k in FIELDS})
    return len(old)

def backfill(key,start,end):
    c=TARGETS[key]
    rows=fundamental(c["market"],c["code"],start,end,[c["api_metric"]])
    if not rows:
        raise RuntimeError(f"no fundamental data returned for {key}")

    debt=[]
    if c.get("extra")=="cn10y":
        debt=national_debt("cn",start,end,["tcm_y10"])
    elif c.get("extra")=="us10y":
        debt=national_debt("us",start,end,["tcm_y10"])

    debt_map={}
    for r in debt:
        if r.get("date") and r.get("tcm_y10") is not None:
            v=float(r["tcm_y10"])
            debt_map[str(r["date"])[:10]]=v*100 if abs(v)<1 else v

    out=[]
    for r in rows:
        d=str(r.get("date",""))[:10]
        if not d: continue
        z={"date":d}; m=c["api_metric"]
        if m.startswith("pe_ttm"): z["pe"]=r.get(m)
        elif m.startswith("pb"): z["pb"]=r.get(m)
        elif m.startswith("ps_ttm"): z["ps"]=r.get(m)
        elif m.startswith("dyr"):
            dv=r.get(m)
            if dv is not None:
                dv=float(dv); z["dividend_yield"]=dv*100 if abs(dv)<1 else dv

        if d in debt_map:
            z[c["extra"]]=debt_map[d]

        if key=="div_lowvol" and z.get("dividend_yield") is not None and z.get("cn10y") is not None:
            z["spread"]=float(z["dividend_yield"])-float(z["cn10y"])

        if key in ("ndx","spx") and z.get("pe") not in (None,0) and z.get("us10y") is not None:
            z["erp"]=100.0/float(z["pe"])-float(z["us10y"])

        out.append(z)

    if not out:
        raise RuntimeError(f"no usable rows after normalization for {key}")
    return write_csv(key,out)

def run_target(key,a,base,ext):
    p=HIST/f"{key}.csv"
    existing=max(0,len(p.read_text(encoding="utf-8").splitlines())-1) if p.exists() else 0

    # First establish a real 5-year history. If it is already sufficient,
    # extend to 10 years in the same run when the API supports it.
    n=backfill(key,base,a.date)
    window=a.years

    if n>=60 and a.extend_years>a.years:
        n=backfill(key,ext,a.date)
        window=a.extend_years

    return {"status":"ok","points":n,"window_years":window,"existing_points_before":existing}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--date",default=datetime.now(TZ).strftime("%Y-%m-%d"))
    ap.add_argument("--years",type=int,default=5)
    ap.add_argument("--extend-years",type=int,default=10)
    a=ap.parse_args()

    status={
        "run_at":datetime.now(TZ).isoformat(timespec="seconds"),
        "requested_window_years":a.years,
        "extended_window_years":a.extend_years,
        "token_configured":bool(token()),
        "targets":{}
    }

    if not token():
        status["status"]="token_missing"
        (DATA/"history_status.json").write_text(
            json.dumps(status,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(status,ensure_ascii=False))
        raise SystemExit(2)

    base=years_ago(a.date,a.years)
    ext=years_ago(a.date,a.extend_years)
    failures=0

    for key in TARGETS:
        try:
            status["targets"][key]=run_target(key,a,base,ext)
        except Exception as e:
            msg=str(e)
            if key=="ndx" and "HTTP 403" in msg:
                status["targets"][key]={"status":"restricted","error":msg,"blocking":False}
            else:
                failures+=1
                status["targets"][key]={"status":"failed","error":msg}
        time.sleep(.25)

    status["status"]="failed" if failures else ("complete_with_anomalies" if any(v.get("status")=="restricted" for v in status["targets"].values()) else "complete")
    status["failed_targets"]=failures
    (DATA/"history_status.json").write_text(
        json.dumps(status,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(status,ensure_ascii=False))

    if failures:
        raise SystemExit(1)

if __name__=="__main__":
    main()
