import requests, json, baostock as bs, pandas as pd
s=requests.get('https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600519&scale=240&ma=no&datalen=1023',headers={'User-Agent':'Mozilla/5.0'},timeout=15).json()
sd={r['day']:float(r['close']) for r in s}
bs.login(); rs=bs.query_history_k_data_plus('sh.600519','date,close',start_date='2024-06-01',end_date='2024-07-10',frequency='d',adjustflag='2')
bq={}
while rs.error_code=='0' and rs.next():
    r=rs.get_row_data(); bq[r[0]]=float(r[1])
rs=bs.query_history_k_data_plus('sh.600519','date,close',start_date='2024-06-01',end_date='2024-07-10',frequency='d',adjustflag='3')
bn={}
while rs.error_code=='0' and rs.next():
    r=rs.get_row_data(); bn[r[0]]=float(r[1])
bs.logout()
for d in sorted(set(sd)&set(bq)):
    if d>='2024-06-15' and d<='2024-07-05':
        print(d,'sina',sd[d],'bs_qfq',bq[d],'bs_raw',bn.get(d),'sina/raw',round(sd[d]/bn[d],4) if bn.get(d) else None)
