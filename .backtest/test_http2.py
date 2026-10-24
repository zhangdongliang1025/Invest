import requests, json
s=requests.Session(); s.trust_env=False; h={'User-Agent':'Mozilla/5.0'}
def get(u):
    r=s.get(u,headers=h,timeout=20); return r
# Tencent variants
for tag,param in [('qfq2000','sh600519,day,2019-01-01,2026-10-24,2000,qfq'),('day2000','sh600519,day,2019-01-01,2026-10-24,2000'),('day800','sh600519,day,2019-01-01,2026-10-24,800'),('qfq800','sh600519,day,2019-01-01,2026-10-24,800,qfq'),('qfq320','sh600519,day,2019-01-01,2026-10-24,320,qfq')]:
    u=f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={param}'
    r=get(u); d=r.json(); key=list(d['data']['sh600519'].keys()); arr=d['data']['sh600519'].get('qfqday') or d['data']['sh600519'].get('day')
    print(tag, key, len(arr), arr[0][0], arr[-1][0])
# Sina larger
for n in [1023,1500,2000]:
    u=f'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600519&scale=240&ma=no&datalen={n}'
    r=get(u); arr=json.loads(r.text); print('sina',n,len(arr),arr[0]['day'],arr[-1]['day'])
