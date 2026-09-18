#!/usr/bin/env python3
import os, requests
from datetime import datetime

BASE="https://open.lixinger.com/api"
S=requests.Session()
S.headers.update({"User-Agent":"InvestmentDashboard/2.0"})

def token():
    return os.environ.get("LIXINGER_TOKEN","").strip()

def request_json(endpoint,payload):
    t=token()
    if not t:
        raise RuntimeError("LIXINGER_TOKEN is not configured")
    body=dict(payload); body["token"]=t
    r=S.post(BASE+endpoint,json=body,timeout=30)
    r.raise_for_status()
    j=r.json()
    if j.get("code") not in (1,"1",None):
        raise RuntimeError(j.get("message") or str(j))
    return j

def fundamental(market,stock_code,start_date,end_date,metrics):
    endpoint="/cn/index/fundamental" if market=="cn" else "/us/index/fundamental"
    return request_json(endpoint,{"startDate":start_date,"endDate":end_date,"stockCodes":[stock_code],"metricsList":metrics}).get("data") or []

def national_debt(area_code,start_date,end_date,metrics):
    return request_json("/macro/national-debt",{"areaCode":area_code,"startDate":start_date,"endDate":end_date,"metricsList":metrics}).get("data") or []

def years_ago(day,years):
    d=datetime.strptime(day,"%Y-%m-%d").date()
    try:return d.replace(year=d.year-years).isoformat()
    except ValueError:return d.replace(year=d.year-years,month=2,day=28).isoformat()
