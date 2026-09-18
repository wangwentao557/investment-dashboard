#!/usr/bin/env python3
import argparse,csv,json,re,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
import requests
ROOT=Path(__file__).resolve().parent; DATA=ROOT/"data"; TZ=timezone(timedelta(hours=8))
S=requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0 InvestmentDashboard/1.0"})
def load(p,d=None): return json.loads(Path(p).read_text(encoding="utf-8")) if Path(p).exists() else d
def dump(p,x): Path(p).parent.mkdir(parents=True,exist_ok=True); Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def fund(code):
    for url,est in [(f"https://fund.eastmoney.com/pingzhongdata/{code}.js",False),(f"https://fundgz.1234567.com.cn/js/{code}.js",True)]:
        try:
            t=S.get(url,timeout=6).text
            if not est:
                n=re.search(r"FundMNAV\s*=\s*([0-9.]+)",t);d=re.search(r"(?:NetWorthDate|FundMNVDate|FundMNAVDate)\s*=\s*["']?([0-9]{4}-[0-9]{2}-[0-9]{2})",t)
                if n and d:return {"nav":float(n.group(1)),"date":d.group(1),"source":"Eastmoney","estimated":False,"fetch_status":"success_actual"}
            else:
                m=re.search(r"jsonpgz\((.*)\)",t)
                if m:
                    o=json.loads(m.group(1));return {"nav":float(o["gsz"]),"date":str(o.get("gztime",""))[:10],"source":"1234567","estimated":True,"fetch_status":"estimated"}
        except Exception:pass
    return {"fetch_status":"failed","failure_reason":"primary and backup source unavailable"}
def lix(url):
    try:
        t=S.get(url,timeout=8).text;d=re.search(r"最后更新于：([0-9-]+)",t);v=re.search(r"当前值[:：]?\s*([0-9.]+)",t);p=re.search(r"当前分位点([0-9.]+)%",t)
        return {"date":d.group(1) if d else None,"value":float(v.group(1)) if v else None,"percentile":float(p.group(1)) if p else None}
    except Exception as e:return {"error":str(e)}
def yahoo(ticker):
    try:
        j=S.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d",timeout=8).json()["chart"]["result"][0];i=len(j["timestamp"])-1
        return {"price":j["indicators"]["quote"][0]["close"][i],"date":datetime.fromtimestamp(j["timestamp"][i],timezone.utc).date().isoformat()}
    except Exception:return {}
def main(day):
    w=load(ROOT/"watchlist.json");p=load(ROOT/"portfolio.json");prev=load(DATA/"market_snapshot_latest.json",{});market={k:dict(v) for k,v in (prev.get("market",{}) or {}).items() if isinstance(v,dict)}
    urls={"div_lowvol":("https://www.lixinger.com/equity/index/detail/csi/H30269/H30269/fundamental/valuation/dyr","dividend_yield"),"hs300":("https://www.lixinger.com/equity/index/detail/sh/000300/300/fundamental/valuation/pe-ttm","pe"),"csi_a50":("https://www.lixinger.com/equity/index/detail/csi/930050/930050/fundamental/valuation/pe-ttm","pe"),"cs_ai":("https://www.lixinger.com/equity/index/detail/csi/930713/930713/fundamental/valuation/ps-ttm","ps"),"hk_internet":("https://www.lixinger.com/equity/index/detail/csi/931637/931637/fundamental/valuation/ps-ttm","ps"),"metals":("https://www.lixinger.com/equity/index/detail/sh/000819/819/fundamental/valuation/pb","pb"),"ndx":("https://www.lixinger.com/equity/index/detail/us/NDX/NDX/fundamental/valuation/pe-ttm","pe"),"spx":("https://www.lixinger.com/equity/index/detail/us/SPX/SPX/fundamental/valuation/pe-ttm","pe")}
    for k,(u,col) in urls.items():
        x=lix(u);d=market.setdefault(k,{"index_name":next(t["name"] for t in w["targets"] if t["key"]==k)});d["fetch_attempt_at"]=datetime.now(TZ).isoformat(timespec="seconds")
        if x.get("value") is not None:d[col]=x["value"];d["date"]=x.get("date") or d.get("date");d["source"]="Lixinger";d["fetch_status"]="success";d[col+"_percentile"]=x.get("percentile")
        else:d["fetch_status"]="failed";d["fetch_error"]=x.get("error","no value")
    for k,t in [("ndx","^NDX"),("spx","^GSPC")]:
        q=yahoo(t);d=market.setdefault(k,{"index_name":k});d["price"]=q.get("price");d["price_date"]=q.get("date")
    q=yahoo("XAUUSD=X");d=market.setdefault("gold",{"index_name":"黄金"});d["gold_usd_oz"]=q.get("price") or d.get("gold_usd_oz");d["date"]=q.get("date") or d.get("date");d["source"]="Yahoo Finance XAUUSD" if q else d.get("source");d["fetch_status"]="success" if q else "stale"
    q=yahoo("^TNX");us10y=q.get("price")/10 if q.get("price") is not None else None
    for k in ("ndx","spx"):
        if us10y is not None:market[k]["us10y"]=us10y
        if market[k].get("pe") and us10y is not None:market[k]["erp"]=(1/market[k]["pe"])*100-us10y
    if market.get("div_lowvol",{}).get("dividend_yield") is not None and market.get("div_lowvol",{}).get("cn10y") is not None:market["div_lowvol"]["spread"]=market["div_lowvol"]["dividend_yield"]-market["div_lowvol"]["cn10y"]
    funds={h["code"]:fund(h["code"]) for h in p["holdings"]}
    dump(DATA/"market_snapshot_latest.json",{"_daily_fetch":{"attempted_at":datetime.now(TZ).isoformat(timespec="seconds"),"data_basis_date":day,"fund_codes_requested":[h["code"] for h in p["holdings"]],"fund_success_count":sum(1 for x in funds.values() if x.get("nav") is not None),"fund_total":len(funds)},"market":market,"funds":funds})
    cols={"div_lowvol":"dividend_yield","hs300":"pe","csi_a50":"pe","cs_ai":"ps","hk_internet":"ps","metals":"pb","ndx":"pe","spx":"pe"}
    for k,col in cols.items():
        d=market.get(k,{})
        if d.get("date")!=day or d.get(col) is None:continue
        path=DATA/"history"/f"{k}.csv";rows=list(csv.DictReader(path.open(encoding="utf-8-sig"))) if path.exists() else [];by={r.get("date"):r for r in rows if r.get("date")};by[day]={"date":day,col:str(d[col])};names=["date",col]
        with path.open("w",newline="",encoding="utf-8") as f:z=csv.DictWriter(f,fieldnames=names);z.writeheader();z.writerows([by[x] for x in sorted(by)])
    subprocess.run([sys.executable,str(ROOT/"valuation_engine.py"),"--config",str(ROOT/"watchlist.json")],check=True)
    hist=load(DATA/"dashboard_history.json",[]);hist=[x for x in hist if x.get("data_basis_date")!=day];holdings=[]
    for h in p["holdings"]:
        x=dict(h);x["market"]=funds[h["code"]];x["weight_pct"]=round(h["holding_value"]/p["account_summary"]["total_assets"]*100,2);holdings.append(x)
    ref=w["allocation_framework"]["reference_pct"];rng=w["allocation_framework"]["range_pct"];by={}
    fund_to_target={}
    for t in w["targets"]:
        for fh in t.get("funds",[]):
            fund_to_target[fh["code"]]=t["key"]
    for h in holdings:
        target=fund_to_target.get(h["code"])
        if target:
            h["valuation_target"]=target
            by[target]=by.get(target,0)+h["weight_pct"]
    reserve=round(sum(h["weight_pct"] for h in holdings if h["code"] not in fund_to_target),2);alloc=[]
    for k in ref:
        cur=reserve if k=="reserve" else by.get(k,0);lo,hi=rng[k];state="within" if lo<=cur<=hi else "below" if cur<lo else "above";alloc.append({"key":k,"current_pct":cur,"reference_pct":ref[k],"range_pct":rng[k],"state":state,"deviation_from_center_pct":round(cur-ref[k],2)})
    an=[]
    for h in holdings:
        if h["market"].get("fetch_status") in ("failed","estimated"):an.append({"target":h["code"],"type":"数据失败或估算","message":"仅保留可靠值/估算值并显式标记，不冒充正式当日净值"})
    for k in cols:
        path=DATA/"history"/f"{k}.csv";n=max(0,len(path.read_text(encoding="utf-8").splitlines())-1) if path.exists() else 0
        if n<60:an.append({"target":k,"type":"历史不足","message":f"当前{n}个真实点，正式L2至少60个"})
    rec={"run_at":datetime.now(TZ).isoformat(timespec="seconds"),"data_basis_date":day,"run_type":"daily_market_and_holdings_update","account_summary":p["account_summary"],"holdings":holdings,"market":market,"allocation_deviation":alloc,"anomalies":an,"completeness":"complete_with_explicit_anomalies" if an else "complete"}
    hist.append(rec);dump(DATA/"dashboard_history.json",hist)
    (DATA/"reports").mkdir(exist_ok=True);(DATA/"reports"/f"盯盘报告_{day}.md").write_text("# 每日盯盘更新 · "+day+"\n\n运行时间："+rec["run_at"]+"\n\n数据完整性："+rec["completeness"]+"\n\n异常：\n"+json.dumps(an,ensure_ascii=False,indent=2),encoding="utf-8")
    subprocess.run([sys.executable,str(ROOT/"sync_site.py")],check=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--date",default=datetime.now(TZ).strftime("%Y-%m-%d"));a=ap.parse_args();main(a.date)
