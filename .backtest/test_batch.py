import requests, json, time, random
from concurrent.futures import ThreadPoolExecutor, as_completed
import akshare as ak
codes = ak.stock_info_a_code_name()
print(codes.shape, codes.head())
syms=[]
for c in codes['code']:
    c=str(c)
    if c.startswith(('60','68')): syms.append('sh'+c)
    elif c.startswith(('00','30')): syms.append('sz'+c)
print('universe',len(syms))
random.seed(1); sample=random.sample(syms,50)
h={'User-Agent':'Mozilla/5.0'}
def fetch(sym):
    u=f'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=1023'
    try:
        r=requests.get(u,headers=h,timeout=15); r.raise_for_status()
        arr=r.json()
        return sym, len(arr), arr[0]['day'] if arr else None, arr[-1]['day'] if arr else None, None
    except Exception as e:
        return sym, 0, None, None, f'{type(e).__name__}:{e}'
t=time.time(); res=[]
with ThreadPoolExecutor(max_workers=12) as ex:
    for f in as_completed([ex.submit(fetch,s) for s in sample]): res.append(f.result())
dt=time.time()-t
ok=[r for r in res if r[4] is None]
bad=[r for r in res if r[4] is not None]
print('sec',round(dt,2),'ok',len(ok),'bad',len(bad),'avg',round(dt/len(sample),3))
print('bad sample',bad[:5])
print('lens',sorted(set(r[1] for r in ok))[:5], sorted(set(r[1] for r in ok))[-5:])
print('dates', ok[0][2], ok[0][3])
