#!/usr/bin/env python3
import argparse,csv,json,re,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
import requests
from lixinger_api import fundamental,national_debt,token

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
TZ=timezone(timedelta(hours=8))
SESSION=requests.Session()
SESSION.headers.update({"User-Agent":"Mozilla/5.0 InvestmentDashboard/3.5"})

TARGETS={
"div_lowvol":("https://www.lixinger.com/equity/index/detail/csi/H30269/H30269/fundamental/valuation/dyr","dividend_yield","H30269"),
"hs300":("https://www.lixinger.com/equity/index/detail/sh/000300/300/fundamental/valuation/pe-ttm","pe","000300"),
"csi_a50":("https://www.lixinger.com/equity/index/detail/csi/930050/930050/fundamental/valuation/pe-ttm","pe","930050"),
"cs_ai":("https://www.lixinger.com/equity/index/detail/csi/930713/930713/fundamental/valuation/ps-ttm","ps","930713"),
"hk_internet":("https://www.lixinger.com/equity/index/detail/csi/931637/931637/fundamental/valuation/ps-ttm","ps","931637"),
"metals":("https://www.lixinger.com/equity/index/detail/sh/000819/819/fundamental/valuation/pb","pb","000819"),
"ndx":("https://www.lixinger.com/equity/index/detail/us/NDX/NDX/fundamental/valuation/pe-ttm","pe",".NDX"),
"spx":("https://www.lixinger.com/equity/index/detail/us/SPX/SPX/fundamental/valuation/pe-ttm","pe",".INX"),
}

def load(path,default=None):
    p=Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

def dump(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")

def ndx_public_pe(day):
    urls=[
        ("https://www.gurufocus.com/economic_indicators/6778/nasdaq-100-pe-ratio","GuruFocus"),
        ("https://trendonify.com/united-states/stock-market/nasdaq-100/pe-ratio","Trendonify")
    ]
    for url,source in urls:
        try:
            r=SESSION.get(url,timeout=15);r.raise_for_status();text=r.text
            m=re.search(r"Nasdaq 100 PE Ratio\s*[:：]\s*([0-9.]+)\s*\(As of\s*([0-9-]+)",text,re.I)
            if not m:
                m=re.search(r"current(?:ly)?[^\n]{0,120}([0-9.]+)",text,re.I)
            if m:
                value=float(m.group(1)); d=m.group(2) if len(m.groups())>1 and m.group(2) else day
                return {"date":d,"pe":value,"source":source+" public fallback","fetch_status":"success_public_fallback","frequency":"daily" if source=="GuruFocus" else "monthly_fallback"}
        except Exception:
            continue
    return {"fetch_status":"failed","failure_reason":"NDX public PE fallback unavailable"}

def public_pe(index_name, day):
    urls = {
        "SPX": [
            ("https://www.gurufocus.com/economic_indicators/57/sp-500-pe-ratio", "GuruFocus"),
            ("https://trendonify.com/united-states/stock-market/pe-ratio", "Trendonify"),
        ],
        "NDX": [
            ("https://www.gurufocus.com/economic_indicators/6778/nasdaq-100-pe-ratio", "GuruFocus"),
            ("https://trendonify.com/united-states/stock-market/nasdaq-100/pe-ratio", "Trendonify"),
        ],
    }.get(index_name, [])
    for url, source in urls:
        try:
            r = SESSION.get(url, timeout=15); r.raise_for_status()
            text = r.text
            m = re.search(r"(?:S&P 500|Nasdaq 100) PE Ratio\s*[:：]\s*([0-9.]+)\s*\(As of\s*([0-9-]+)", text, re.I)
            if m:
                return {"date": m.group(2), "pe": float(m.group(1)), "source": source + " public fallback", "fetch_status": "success_public_fallback"}
        except Exception:
            continue
    return {"fetch_status":"failed","failure_reason":f"{index_name} public PE fallback unavailable"}

def public_page(url):
    try:
        r=SESSION.get(url,timeout=15);r.raise_for_status();text=r.text
        d=re.search(r"最后更新于：([0-9]{4}-[0-9]{2}-[0-9]{2})",text)
        vals=re.findall(r"当前值[:：]?\s*([0-9.]+)",text)
        p=re.findall(r"当前分位点\s*([0-9.]+)%",text)
        return {"date":d.group(1) if d else None,"value":float(vals[0]) if vals else None,"percentile":float(p[0]) if p else None}
    except Exception as e:
        return {"error":str(e)}

def api_current(day,key,target):
    start=(datetime.strptime(day,"%Y-%m-%d").date()-timedelta(days=7)).isoformat()
    if key=="spx":
        pe=public_pe("SPX",day)
        if pe.get("pe") is None:return pe
        try:
            j=SESSION.get("https://query1.finance.yahoo.com/v8/finance/chart/^TNX?range=5d&interval=1d",timeout=10).json()["chart"]["result"][0]
            i=len(j["timestamp"])-1;us10y=float(j["indicators"]["quote"][0]["close"][i])/10
            us_date=datetime.fromtimestamp(j["timestamp"][i],timezone.utc).date().isoformat()
            pe["us10y"]=us10y;pe["us10y_date"]=us_date;pe["erp"]=100/float(pe["pe"])-us10y;pe["erp_date"]=pe["date"]
        except Exception as e:
            pe["fetch_status"]="stale_failed";pe["fetch_error"]=str(e)
        return pe
    if key=="div_lowvol":
        rows=fundamental("cn","H30269",start,day,["dyr.mcw"])
        rows=sorted(rows,key=lambda x:str(x.get("date","")))
        row=rows[-1] if rows else {}
        if not row or row.get("dyr.mcw") is None:
            return {"fetch_status":"failed","failure_reason":"Lixinger returned no dividend_yield row in last 7 days"}
        debt=national_debt("cn",start,day,["tcm_y10"])
        d={"date":str(row.get("date",""))[:10],"source":"Lixinger API","source_url":"https://open.lixinger.com/api/cn/index/fundamental","fetch_status":"success_actual","dividend_yield":float(row["dyr.mcw"])*100 if abs(float(row["dyr.mcw"]))<1 else float(row["dyr.mcw"])}
        debt=sorted(debt,key=lambda x:str(x.get("date",""))) if debt else []
        if debt and debt[-1].get("tcm_y10") is not None:
            d["cn10y"]=float(debt[-1]["tcm_y10"])*100 if abs(float(debt[-1]["tcm_y10"]))<1 else float(debt[-1]["tcm_y10"])
            d["spread"]=d["dividend_yield"]-d["cn10y"];d["spread_date"]=d["date"]
        return d
    code=target["index"]["code"]
    api_code=code if key not in ("ndx","spx") else (".NDX" if key=="ndx" else ".INX")
    pm={"pe_percentile":"pe_ttm.mcw","ps_percentile":"ps_ttm.mcw","pb_percentile":"pb.mcw"}.get(target["primary_metric"])
    if pm is None:
        return {"fetch_status":"failed","failure_reason":"unsupported primary metric"}
    base=pm.split(".")[0]
    metrics=[pm,base+".y3.mcw.cvpos",base+".y5.mcw.cvpos",base+".y10.mcw.cvpos"]
    rows=fundamental("cn" if key not in ("ndx","spx") else "us",api_code,start,day,metrics)
    rows=sorted(rows,key=lambda x:str(x.get("date","")))
    row=rows[-1] if rows else {}
    if not row or row.get(pm) is None:
        return {"fetch_status":"failed","failure_reason":"Lixinger returned no primary metric row in last 7 days"}
    d={"date":str(row.get("date",""))[:10],"source":"Lixinger API","source_url":"https://open.lixinger.com/api/cn/index/fundamental","fetch_status":"success_actual"}
    d[target["primary_metric"].split("_")[0]]=float(row[pm])
    metric_prefix={"pe_percentile":"pe","ps_percentile":"ps","pb_percentile":"pb"}[target["primary_metric"]]
    for y in (3,5,10):
        v=row.get(base+".y"+str(y)+".mcw.cvpos")
        if v is not None:d[metric_prefix+"_"+str(y)+"y_percentile"]=float(v)*100
    v5=row.get(base+".y5.mcw.cvpos")
    if v5 is not None:d[target["primary_metric"]]=float(v5)*100
    if key in ("ndx","spx"):
        debt=national_debt("us",start,day,["tcm_y10"])
        debt=sorted(debt,key=lambda x:str(x.get("date",""))) if debt else []
        if debt and debt[-1].get("tcm_y10") is not None:
            d["us10y"]=float(debt[-1]["tcm_y10"])*100 if abs(float(debt[-1]["tcm_y10"]))<1 else float(debt[-1]["tcm_y10"])
            d["us10y_date"]=debt[-1].get("date",d["date"])
        if d.get("pe") not in (None,0) and d.get("us10y") is not None:
            d["erp"]=100/float(d["pe"])-d["us10y"];d["erp_date"]=d["date"]
    return d

def fund(code, target_day):
    url=f"https://fund.eastmoney.com/pingzhongdata/{code}.js?v={int(datetime.now().timestamp())}"
    try:
        t=SESSION.get(url,timeout=15).text
        m=re.search(r"Data_netWorthTrend\s*=\s*(\[\{.*?\}\]);",t,re.S)
        if not m:
            raise RuntimeError("Eastmoney Data_netWorthTrend not found")
        rows=json.loads(m.group(1))
        candidates=[]
        for row in rows:
            ts=row.get("x")
            nav=row.get("y")
            if ts is None or nav is None: continue
            d=datetime.fromtimestamp(float(ts)/1000,timezone.utc).date().isoformat()
            if d<=target_day:
                candidates.append((d,float(nav)))
        if not candidates:
            raise RuntimeError(f"no settled NAV on/before {target_day}")
        d,nav=max(candidates,key=lambda x:x[0])
        return {"nav":nav,"date":d,"source":"Eastmoney Data_netWorthTrend","source_url":url,"fetch_status":"success_actual","estimated":False}
    except Exception as e:
        return {"fetch_status":"failed","failure_reason":str(e),"estimated":False}

def append_point(key,col,day,market,date_field="date"):
    d=market.get(key,{})
    if d.get(date_field)!=day or d.get(col) is None:return False
    p=DATA/"history"/f"{key}.csv";p.parent.mkdir(parents=True,exist_ok=True)
    old={}
    if p.exists():
        with p.open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r.get("date"):old[r["date"]]=r
    old[day]={"date":day,col:str(d[col])}
    fields=["date","pe","pb","ps","dividend_yield","cn10y","spread","us10y","erp"]
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for date in sorted(old):w.writerow({k:old[date].get(k,"") for k in fields})
    return True

def main(day):
    is_historical = day < datetime.now(TZ).strftime("%Y-%m-%d")
    watch=load(ROOT/"watchlist.json",{})
    portfolio=load(ROOT/"portfolio.json",{})
    prev=load(DATA/"market_snapshot_latest.json",{"market":{}})
    prev_market=prev.get("market",{}) or {}
    market={k:dict(v) for k,v in prev_market.items() if isinstance(v,dict)}

    for key,(url,col,_) in TARGETS.items():
        target=next(t for t in watch["targets"] if t["key"]==key)
        if token():
            try:
                fresh=api_current(day,key,target)
                market[key]=dict(market.get(key,{}));market[key].update(fresh)
                if fresh.get("fetch_status")=="success_actual":
                    market[key].pop("failure_reason",None);market[key].pop("fetch_error",None)
                if key=="ndx" and market[key].get("fetch_status")=="failed":
                    fb=ndx_public_pe(day)
                    if fb.get("pe") is not None: market[key].update(fb)
            except Exception as e:
                if key=="ndx":
                    fb=ndx_public_pe(day)
                    if fb.get("pe") is not None:
                        market[key]=dict(market.get(key,{}));market[key].update(fb)
                    else:
                        market[key]["fetch_status"]="stale_failed";market[key]["fetch_error"]=str(e)
                else:
                    market[key]["fetch_status"]="stale_failed";market[key]["fetch_error"]=str(e)
        else:
            q=public_page(url);d=market.setdefault(key,{})
            if q.get("value") is not None:
                d[col]=q["value"];d["date"]=q.get("date") or d.get("date");d["source"]="Lixinger public page";d["fetch_status"]="success_public_page";d["pe_percentile"]=q.get("percentile")
            else:
                d["fetch_status"]="stale_failed";d["fetch_error"]=q.get("error","no value")

    # Public-source fallback for overseas macro inputs and gold.
    if not token():
        try:
            j=SESSION.get("https://query1.finance.yahoo.com/v8/finance/chart/^TNX?range=5d&interval=1d",timeout=10).json()["chart"]["result"][0]
            i=len(j["timestamp"])-1;us10y=float(j["indicators"]["quote"][0]["close"][i])/10
            us_date=datetime.fromtimestamp(j["timestamp"][i],timezone.utc).date().isoformat()
            for k in ("ndx","spx"):
                d=market.setdefault(k,{})
                d["us10y"]=us10y;d["us10y_date"]=us_date
                if d.get("pe") not in (None,0) and d.get("date")==us_date:
                    d["erp"]=100/float(d["pe"])-us10y;d["erp_date"]=us_date
        except Exception:
            pass
    try:
        j=SESSION.get("https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X?range=5d&interval=1d",timeout=10).json()["chart"]["result"][0]
        i=len(j["timestamp"])-1;g=float(j["indicators"]["quote"][0]["close"][i])
        gd=datetime.fromtimestamp(j["timestamp"][i],timezone.utc).date().isoformat()
        market.setdefault("gold",{})["index_name"]="黄金";market["gold"]["gold_usd_oz"]=g;market["gold"]["date"]=gd;market["gold"]["source"]="Yahoo Finance";market["gold"]["fetch_status"]="success"
    except Exception:
        if "gold" in market:market["gold"]["fetch_status"]="stale"
    funds={h["code"]:fund(h["code"],day) for h in portfolio["holdings"]}
    for key,col,date_field in [("div_lowvol","spread","spread_date"),("hs300","pe","date"),("csi_a50","pe","date"),("cs_ai","ps","date"),("hk_internet","ps","date"),("metals","pb","date"),("ndx","erp","erp_date"),("spx","erp","erp_date")]:
        append_point(key,col,day,market,date_field)

    actual_dates=[]
    for v in funds.values():
        if v.get("fetch_status")=="success_actual" and v.get("date"): actual_dates.append(v["date"])
    for v in market.values():
        if v.get("fetch_status") in ("success_actual","success_public_fallback","success_public_page") and v.get("date"): actual_dates.append(v["date"])
    latest_actual_date=max(actual_dates) if actual_dates else day
    snapshot={
        "_daily_fetch":{
            "attempted_at":datetime.now(TZ).isoformat(timespec="seconds"),
            "requested_date":day,
            "data_basis_date":latest_actual_date,
            "fund_codes_requested":[h["code"] for h in portfolio["holdings"]],
            "fund_success_count":sum(1 for x in funds.values() if x.get("nav") is not None),
            "fund_total":len(funds),
            "lixinger_api_configured":bool(token())
        },
        "market":market,
        "funds":funds
    }
    if not is_historical:
        dump(DATA/"market_snapshot_latest.json",snapshot)

    subprocess.run([sys.executable,str(ROOT/"valuation_engine.py"),"--config",str(ROOT/"watchlist.json")],check=True)
    l2=load(DATA/"l2_latest.json",{})

    hist_raw=load(DATA/"dashboard_history.json",[]) or []
    hist=hist_raw.get("records",[]) if isinstance(hist_raw,dict) else hist_raw
    hist=[x for x in hist if isinstance(x,dict) and x.get("data_basis_date")!=day]
    total=sum(float(h.get("holding_value",0)) for h in portfolio.get("holdings",[]))
    holdings=[]
    fund_to_target={}
    for t in watch["targets"]:
        for fh in t.get("funds",[]):fund_to_target[fh["code"]]=t["key"]
    by={}
    for h in portfolio["holdings"]:
        x=dict(h);x["market"]=funds.get(h["code"],{});x["weight_pct"]=round(float(h["holding_value"])/total*100,2)
        x["valuation_target"]=fund_to_target.get(h["code"])
        holdings.append(x)
        if x["valuation_target"]:by[x["valuation_target"]]=by.get(x["valuation_target"],0)+x["weight_pct"]

    ref=watch["allocation_framework"]["reference_pct"];rng=watch["allocation_framework"]["range_pct"]
    alloc=[]
    for key in ref:
        cur=round(by.get(key,0),2)
        lo,hi=rng[key];state="within" if lo<=cur<=hi else "below" if cur<lo else "above"
        alloc.append({"key":key,"current_pct":cur,"reference_pct":ref[key],"range_pct":rng[key],"state":state,"deviation_from_center_pct":round(cur-ref[key],2)})

    anomalies=[]
    for h in holdings:
        st=h["market"].get("fetch_status")
        if st in ("failed","estimated","stale_failed"):
            anomalies.append({"target":h["code"],"type":"基金数据","message":st+"；当前值不作为当日正式净值"})
    for key in ["div_lowvol","hs300","csi_a50","cs_ai","hk_internet","metals","ndx","spx"]:
        p=DATA/"history"/f"{key}.csv"
        points=max(0,len(p.read_text(encoding="utf-8").splitlines())-1) if p.exists() else 0
        if points<60:anomalies.append({"target":key,"type":"历史不足","message":f"当前{points}个真实点；正式L2需要至少60个真实点"})

    rec={
        "run_at":snapshot["_daily_fetch"]["attempted_at"],"data_basis_date":snapshot["_daily_fetch"]["data_basis_date"],
        "run_type":"daily_market_and_holdings_update",
        "account_summary":portfolio["account_summary"],"fund_success_count":snapshot["_daily_fetch"]["fund_success_count"],
        "fund_total":snapshot["_daily_fetch"]["fund_total"],"holdings":holdings,"market":market,
        "allocation_deviation":alloc,"l2":l2,"anomalies":anomalies,
        "completeness":"complete_with_explicit_anomalies" if anomalies else "complete"
    }
    hist.append(rec);dump(DATA/"dashboard_history.json",{"records":hist})

    reports=DATA/"reports";reports.mkdir(exist_ok=True)
    lines=["# 每日盯盘更新 · "+day,"","运行时间："+rec["run_at"],"数据完整性："+rec["completeness"],f"持仓数据：{rec['fund_success_count']}/{rec['fund_total']}","",
           "## 9个估值"]
    for t in watch["targets"]:
        x=market.get(t["key"],{});z=l2.get("targets",{}).get(t["key"],{}) if isinstance(l2,dict) else {}
        lines.append(f"- {t['name']}：日期={x.get('date','—')} 状态={x.get('fetch_status','—')} L2={z.get('signal','no_data')} 点数={z.get('points',0)}")
    lines += ["","## 异常",json.dumps(anomalies,ensure_ascii=False,indent=2)]
    (reports/f"盯盘报告_{day}.md").write_text("\n".join(lines),encoding="utf-8")
    if not is_historical:
        subprocess.run([sys.executable,str(ROOT/"sync_site.py")],check=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--date",default=datetime.now(TZ).strftime("%Y-%m-%d"));main(ap.parse_args().date)
