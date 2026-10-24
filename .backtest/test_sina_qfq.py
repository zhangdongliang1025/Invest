import requests, json, re, pandas as pd
h={'User-Agent':'Mozilla/5.0'}
def kline(sym):
    u=f'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=1023'
    r=requests.get(u,headers=h,timeout=15); return r.text
def qfq(sym):
    u=f'https://finance.sina.com.cn/realstock/company/{sym}/qfq.js'
    r=requests.get(u,headers=h,timeout=15); return r.status_code, r.text[:200]
for sym in ['sh600519','sz000667','sh600823','sz002433','sz300750']:
    try:
        t=kline(sym); print(sym,'kline',len(t),t[:80])
    except Exception as e: print(sym,'kline ERR',e)
    try:
        st,t=qfq(sym); print(sym,'qfq',st,len(t),t[:160])
    except Exception as e: print(sym,'qfq ERR',e)
