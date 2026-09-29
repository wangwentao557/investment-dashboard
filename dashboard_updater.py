#!/usr/bin/env python3
import argparse,csv,io,json,re,subprocess,sys
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
            ("https://www.multpl.com/s-p-500-pe-ratio/table/by-month", "Multpl"),
        ],
        "NDX": [
            ("https://www.gurufocus.com/economic_indicators/6778/nasdaq-100-pe-ratio", "GuruFocus"),
            ("https://trendonify.com/united-states/stock-market/nasdaq-100/pe-ratio", "Trendonify"),
        ],
    }.get(index_name, [])
    for url, source in urls:
        try:
            r = SESSION.get(url, timeout=15); r.raise_for_status(); text = r.text
            patterns = [
                r"(?:S&P 500|Nasdaq 100) PE Ratio\s*[:：]\s*([0-9.]+)\s*\(As of\s*([0-9-]+)",
                r"(?:S&P 500|Nasdaq 100) PE Ratio[^0-9]{0,80}([0-9.]+)[^0-9]{0,80}(?:As of|as of)[^0-9]{0,10}([0-9]{4}-[0-9]{2}-[0-9]{2})",
            ]
            m = None
            for pat in patterns:
                m = re.search(pat, text, re.I|re.S)
                if m: break
            if m:
                return {"date":m.group(2),"pe":float(m.group(1)),"source":source+" public fallback","fetch_status":"success_public_fallback","source_url":url,"estimated":False}
            if index_name=="SPX" and source=="Multpl":
                # 原先此处硬编码了某一天日期，仅在当天有效；改为动态取最新一期
                _MON={m2:i+1 for i,m2 in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"])}
                _mm=re.findall(r"([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})[^0-9]{0,120}?([0-9]+\.[0-9]+)",text)
                if _mm:
                    _best=max(_mm,key=lambda x:(int(x[2]),_MON.get(x[0],0),int(x[1])))
                    _d=datetime(int(_best[2]),_MON.get(_best[0],1),int(_best[1])).date().isoformat()
                    return {"date":_d,"pe":float(_best[3]),"source":"Multpl public estimate","fetch_status":"success_public_estimate","source_url":url,"estimated":True}
            if index_name=="NDX" and source=="Trendonify":
                m=re.search(r"current(?:ly)? trades at a current P/E ratio of\s*([0-9.]+)\s*as of\s*([A-Za-z]+\s+[0-9]+,\s+[0-9]{4})",text,re.I)
                if m:
                    d=datetime.strptime(m.group(2),"%B %d, %Y").date().isoformat()
                    return {"date":d,"pe":float(m.group(1)),"source":"Trendonify public fallback","fetch_status":"success_public_fallback","source_url":url,"methodology":"Trendonify"}
        except Exception:
            continue
    return {"fetch_status":"failed","failure_reason":f"{index_name} public PE fallback unavailable"}
def gold_public(day):
    # 首选：新浪财经 hf_XAU（国内可达；原 Yahoo 源在当前网络下返回 403）
    try:
        r=SESSION.get("https://hq.sinajs.cn/list=hf_XAU",headers={"Referer":"https://finance.sina.com.cn"},timeout=12)
        m=re.search(r'hq_str_hf_XAU="([^"]*)"',r.text)
        if m:
            parts=m.group(1).split(",")
            if len(parts)>12 and parts[0] not in ("","0"):
                return {"index_name":"黄金","gold_usd_oz":float(parts[0]),"date":parts[12],
                        "source":"Sina hf_XAU (伦敦金现)","source_url":"https://hq.sinajs.cn/list=hf_XAU",
                        "fetch_status":"success_actual","estimated":False}
    except Exception:
        pass
    # 次选：上金所 Au99.99（人民币/克，用于国内金价交叉校验）
    try:
        r=SESSION.get("https://hq.sinajs.cn/list=SGE_AU9999",headers={"Referer":"https://finance.sina.com.cn"},timeout=12)
        m=re.search(r'hq_str_SGE_AU9999="([^"]*)"',r.text)
        if m:
            parts=m.group(1).split(",")
            if len(parts)>16 and parts[3] not in ("","0"):
                return {"index_name":"黄金","gold_cny_gram":float(parts[3]),"date":parts[16].split(" ")[0],
                        "source":"Sina SGE_AU9999 (上金所)","source_url":"https://hq.sinajs.cn/list=SGE_AU9999",
                        "fetch_status":"success_public_fallback","estimated":False}
    except Exception:
        pass
    sources=[
        ("https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X?range=10d&interval=1d","Yahoo Finance"),
        ("https://query2.finance.yahoo.com/v8/finance/chart/XAUUSD=X?range=10d&interval=1d","Yahoo Finance query2"),
    ]
    for url,source in sources:
        try:
            j=SESSION.get(url,timeout=12).json()["chart"]["result"][0]
            ts=j.get("timestamp",[]); cl=j.get("indicators",{}).get("quote",[{}])[0].get("close",[])
            rows=[]
            for t,v in zip(ts,cl):
                if v is None: continue
                d=datetime.fromtimestamp(t,timezone.utc).date().isoformat()
                if d<=day: rows.append((d,float(v)))
            if rows:
                d,v=max(rows,key=lambda x:x[0])
                return {"index_name":"黄金","gold_usd_oz":v,"date":d,"source":source,"source_url":url,"fetch_status":"success_actual","estimated":False}
        except Exception:
            continue
    # Last-resort public historical page fallback; value remains explicitly source-attributed.
    try:
        url="https://www.investing.com/currencies/xau-usd-historical-data"
        text=SESSION.get(url,timeout=15).text
        m=re.search(r"(?:Sep|September)\\s+25,?\\s+2026[^0-9]{0,120}([0-9,]+\\.[0-9]+)",text,re.I)
        if m:
            v=float(m.group(1).replace(",",""))
            return {"index_name":"黄金","gold_usd_oz":v,"date":"2026-09-25","source":"Investing.com public historical","source_url":url,"fetch_status":"success_public_fallback","estimated":False}
    except Exception:
        pass
    # Historical daily close fallback from GoldPrice.org; search backward up to 7 days.
    for delta in range(0,8):
        try:
            d=(datetime.strptime(day,"%Y-%m-%d").date()-timedelta(days=delta)).isoformat()
            url=f"https://goldprice.org/gold-price-today/{d}"
            text=SESSION.get(url,timeout=15).text
            m=re.search(r"Gold Price\\s*\\|\\s*([0-9,]+\\.[0-9]+)",text,re.I)
            if m:
                return {"index_name":"黄金","gold_usd_oz":float(m.group(1).replace(",","")),"date":d,"source":"GoldPrice.org public historical","source_url":url,"fetch_status":"success_public_fallback","estimated":False}
        except Exception:
            continue
    return {"fetch_status":"failed","failure_reason":"Gold public sources unavailable"}

US_TREASURY_URL="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv"

# 纳指 PE 锚点：锚点日必须同时有「官方 PE」与「当日指数收盘」
NDX_ANCHOR={"date":"2026-09-18","pe":29.13,"price":29644.17,"source":"公开核验快照"}

def us_treasury_10y():
    """美国财政部官方每日国债收益率曲线（10Y）。替代被墙的 Yahoo ^TNX。"""
    y=datetime.now(TZ).strftime("%Y")
    url=US_TREASURY_URL.format(y=y)
    try:
        r=SESSION.get(url,timeout=25);r.raise_for_status()
        rd=list(csv.reader(io.StringIO(r.text)))
        if not rd: raise RuntimeError("empty csv")
        header=rd[0]
        idx=None
        for i,h in enumerate(header):
            if h.strip().replace(" ","").lower() in ("10yr","10year","10years"):
                idx=i;break
        if idx is None:
            for i,h in enumerate(header):
                if h.strip().startswith("10"):idx=i;break
        rows=[]
        for row in rd[1:]:
            if len(row)>idx and row[idx] and row[0]:
                try:
                    dt=datetime.strptime(row[0].strip(),"%m/%d/%Y")
                except Exception:
                    continue
                rows.append((dt,float(row[idx])))
        if not rows: raise RuntimeError("no rows")
        rows.sort(key=lambda x:x[0])
        dt,v=rows[-1]
        return {"us10y":v,"us10y_date":dt.date().isoformat(),"source":"US Treasury daily yield curve","source_url":url,"fetch_status":"success_actual"}
    except Exception as e:
        return {"us10y":None,"fetch_status":"failed","failure_reason":str(e)}

# 标普 PE 锚点（锚点日同时有官方 PE 与当日指数收盘）
SPX_ANCHOR={"date":"2026-09-25","pe":26.4,"price":7743.41,"source":"Multpl public estimate / 新华社收盘"}

def spx_price():
    """新浪财经 标普500 实时点位。"""
    try:
        r=SESSION.get("https://hq.sinajs.cn/list=gb_inx",headers={"Referer":"https://finance.sina.com.cn"},timeout=12)
        m=re.search(r'hq_str_gb_inx="([^"]*)"',r.text)
        if m:
            parts=m.group(1).split(",")
            if len(parts)>3 and parts[1]:
                return {"price":float(parts[1]),"pct":float(parts[2]) if parts[2] else None,"quote_time":parts[3],"source":"Sina gb_inx"}
    except Exception:
        pass
    return None

def spx_estimated_pe(day):
    """标普PE：锚点 × 指数涨跌比例（EPS 短期近似不变）。"""
    q=spx_price()
    if not q or not q.get("price"):
        return {"fetch_status":"failed","failure_reason":"SPX price source unavailable"}
    pe=round(SPX_ANCHOR["pe"]*q["price"]/SPX_ANCHOR["price"],2)
    return {"index_name":"标普500","pe":pe,"date":day,
            "source":"价格推算(锚点 %s PE=%s @%.2f)"%(SPX_ANCHOR["date"],SPX_ANCHOR["pe"],SPX_ANCHOR["price"]),
            "fetch_status":"success_public_estimate","estimated":True,
            "estimate_method":"anchor_PE × (price_now / price_anchor)",
            "anchor":dict(SPX_ANCHOR),"spx_price":q["price"],"spx_price_time":q.get("quote_time")}

def us10y_yahoo():
    """Yahoo ^TNX（在 GitHub Actions 环境下可用）。"""
    for host in ("query1","query2"):
        try:
            j=SESSION.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/%5ETNX?range=5d&interval=1d",timeout=12).json()["chart"]["result"][0]
            i=len(j["timestamp"])-1
            v=j["indicators"]["quote"][0]["close"][i]
            if v is None: continue
            d=datetime.fromtimestamp(j["timestamp"][i],timezone.utc).date().isoformat()
            return {"us10y":float(v),"us10y_date":d,"source":"Yahoo ^TNX","fetch_status":"success_actual"}
        except Exception:
            continue
    return {"us10y":None,"fetch_status":"failed","failure_reason":"yahoo ^TNX unavailable"}

def us10y_best():
    """美债10Y：Yahoo 优先，美国财政部官方 CSV 兜底。"""
    for fn in (us10y_yahoo,us_treasury_10y):
        try:
            r=fn()
        except Exception:
            continue
        if isinstance(r,dict) and r.get("us10y") is not None:
            return r
    return {"us10y":None,"fetch_status":"failed","failure_reason":"all us10y sources failed"}

def ndx_price():
    """新浪财经 纳斯达克100 实时点位。"""
    try:
        r=SESSION.get("https://hq.sinajs.cn/list=gb_ndx",headers={"Referer":"https://finance.sina.com.cn"},timeout=12)
        m=re.search(r'hq_str_gb_ndx="([^"]*)"',r.text)
        if m:
            parts=m.group(1).split(",")
            if len(parts)>3 and parts[1]:
                return {"price":float(parts[1]),"pct":float(parts[2]) if parts[2] else None,
                        "quote_time":parts[3],"source":"Sina gb_ndx"}
    except Exception:
        pass
    return None

def ndx_estimated_pe(day):
    """纳指PE：以锚点(PE,指数)为基准，按指数涨跌比例推算（EPS 短期近似不变）。
    月度用官方PE校准即可持续对齐。明确标注 estimated=True。"""
    q=ndx_price()
    if not q or not q.get("price"):
        return {"fetch_status":"failed","failure_reason":"NDX price source unavailable"}
    pe=round(NDX_ANCHOR["pe"]*q["price"]/NDX_ANCHOR["price"],2)
    return {"index_name":"纳斯达克100","pe":pe,"date":day,
            "source":"价格推算(锚点 %s PE=%s @%.2f)"%(NDX_ANCHOR["date"],NDX_ANCHOR["pe"],NDX_ANCHOR["price"]),
            "fetch_status":"success_public_estimate","estimated":True,
            "estimate_method":"anchor_PE × (price_now / price_anchor)",
            "anchor":dict(NDX_ANCHOR),"ndx_price":q["price"],"ndx_price_time":q.get("quote_time")}

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
        if pe.get("pe") is None: pe=spx_estimated_pe(day)
        if pe.get("pe") is None:return pe
        try:
            t=us10y_best()
            if t.get("us10y") is None: raise RuntimeError("us10y sources unavailable")
            pe["us10y"]=t["us10y"];pe["us10y_date"]=t["us10y_date"]
            pe["erp"]=100/float(pe["pe"])-t["us10y"];pe["erp_date"]=pe["date"]
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
    d={"date":str(row.get("date",""))[:10],"source":"Lixinger API","source_url":("https://open.lixinger.com/api/us/index/fundamental" if key in ("ndx","spx") else "https://open.lixinger.com/api/cn/index/fundamental"),"fetch_status":"success_actual"}
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
            d=datetime.fromtimestamp(float(ts)/1000,TZ).date().isoformat()
            if d<=target_day:
                candidates.append((d,float(nav)))
        if not candidates:
            raise RuntimeError(f"no settled NAV on/before {target_day}")
        d,nav=max(candidates,key=lambda x:x[0])
        prev=max([c for c in candidates if c[0]<d],key=lambda x:x[0]) if len(candidates)>1 else (d,nav)
        return {"nav":nav,"date":d,"prev_nav":prev[1],"prev_date":prev[0],
                "nav_map":{dd:vv for dd,vv in candidates[-90:]},
                "source":"Eastmoney Data_netWorthTrend","source_url":url,"fetch_status":"success_actual","estimated":False}
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
                if fresh.get("fetch_status") in ("success_actual","success_public_fallback","success_public_estimate"):
                    market[key].pop("failure_reason",None);market[key].pop("fetch_error",None)
                if key=="ndx" and market[key].get("fetch_status") in ("failed","stale_failed"):
                    fb=ndx_public_pe(day)
                    if fb.get("pe") is None: fb=ndx_estimated_pe(day)
                    market[key]=dict(market.get(key,{}));market[key].update(fb)
            except Exception as e:
                if key=="ndx":
                    fb=ndx_public_pe(day)
                    if fb.get("pe") is None: fb=ndx_estimated_pe(day)
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
    gold=gold_public(day)
    if gold.get("fetch_status")=="success_actual":
        market["gold"]=gold
    else:
        old=market.get("gold",{})
        old["fetch_status"]="stale"
        old["failure_reason"]=gold.get("failure_reason","gold fetch failed")
        market["gold"]=old
    funds={h["code"]:fund(h["code"],day) for h in portfolio["holdings"]}
    # 待入账买入：净值确认后自动折算份额（T日买入按T日净值），入账后从 pending 移除
    for h in portfolio["holdings"]:
        f=funds.get(h["code"],{}) or {};nm=f.get("nav_map",{}) or {}
        keep=[]
        for pb in list(h.get("pending_buys",[]) or []):
            nav=nm.get(pb.get("date"))
            if nav:
                add=round(float(pb["amount"])/float(nav),6)
                h["shares"]=round(float(h.get("shares",0))+add,6)
                h.setdefault("shares_history",[]).append({"date":pb["date"],"action":"buy","amount":pb["amount"],"nav":nav,"shares_added":add})
            else:
                keep.append(pb)
        if keep: h["pending_buys"]=keep
        elif "pending_buys" in h: h.pop("pending_buys")
    for key,col,date_field in [("div_lowvol","spread","spread_date"),("hs300","pe","date"),("csi_a50","pe","date"),("cs_ai","ps","date"),("hk_internet","ps","date"),("metals","pb","date"),("ndx","erp","erp_date"),("spx","erp","erp_date")]:
        append_point(key,col,day,market,date_field)

    actual_dates=[]
    for v in funds.values():
        if v.get("fetch_status")=="success_actual" and v.get("date"): actual_dates.append(v["date"])
    for v in market.values():
        if v.get("fetch_status") in ("success_actual","success_public_fallback","success_public_page","success_public_estimate") and v.get("date") and not v.get("estimated"): actual_dates.append(v["date"])
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
    holdings=[];fund_to_target={}
    for t in watch["targets"]:
        for fh in t.get("funds",[]):fund_to_target[fh["code"]]=t["key"]
    live_value={};today_pnl=0.0;nav_basis=set()
    for h in portfolio.get("holdings",[]):
        f=funds.get(h["code"],{}) or {}
        sh=h.get("shares")
        if sh and f.get("nav"):
            live_value[h["code"]]=round(float(sh)*float(f["nav"]),2)
            nav_basis.add(str(f.get("date")))
            if f.get("prev_nav"):
                today_pnl+=float(sh)*(float(f["nav"])-float(f["prev_nav"]))
        else:
            live_value[h["code"]]=float(h.get("holding_value",0))
    total=round(sum(live_value.values()),2)
    by={}
    for h in portfolio["holdings"]:
        x=dict(h);x["market"]=funds.get(h["code"],{})
        x["holding_value"]=live_value.get(h["code"],float(h.get("holding_value",0)))
        if x.get("shares") and (funds.get(h["code"],{}) or {}).get("nav"):
            x["holding_value_basis"]="shares×nav@"+str(funds[h["code"]].get("date"))
        x["weight_pct"]=round(float(x["holding_value"])/total*100,2) if total else 0
        x["valuation_target"]=fund_to_target.get(h["code"])
        holdings.append(x)
        if x["valuation_target"]:by[x["valuation_target"]]=by.get(x["valuation_target"],0)+x["weight_pct"]
    _cb=portfolio.get("account_summary",{}).get("cost_basis")
    cost_basis=float(_cb) if _cb not in (None,"") else total
    portfolio["account_summary"]={
        "total_assets":total,
        "today_pnl":round(today_pnl,2),
        "total_pnl":round(total-cost_basis,2),
        "cost_basis":round(cost_basis,2),
        "nav_basis_dates":sorted(nav_basis),
        "pending_buys":sum(len(h.get("pending_buys",[]) or []) for h in portfolio.get("holdings",[])),
        "note":"total_assets/today_pnl 由脚本按 shares×nav 自动计算；cost_basis 手工维护（总投入本金）",
    }

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
    for key,v in market.items():
        if not isinstance(v,dict):continue
        st=v.get("fetch_status");dt=v.get("date") or v.get("erp_date") or v.get("spread_date")
        if st in ("stale","stale_failed") or (st=="failed"):
            anomalies.append({"target":key,"type":"数据陈旧","message":f"最新数据日期 {dt or '—'}（状态 {st}），未更新到 {day}"})
        elif v.get("estimated") and dt and dt<day:
            anomalies.append({"target":key,"type":"估算值","message":f"{dt} 为估算数据（{v.get('source')}），非官方口径"})
    for h in holdings:
        if not h.get("valuation_target"):
            anomalies.append({"target":h["code"],"type":"无估值目标","message":h["name"]+" 未纳入估值雷达（valuation_target 为空）"})
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
    if not is_historical:
        dump(ROOT/"portfolio.json",portfolio)

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
