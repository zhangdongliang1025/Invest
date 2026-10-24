import requests, time, json
s = requests.Session(); s.trust_env = False
h = {'User-Agent':'Mozilla/5.0'}
urls = {
 'sina_kline': 'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600519&scale=240&ma=no&datalen=1023',
 'tx_kline': 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,2019-01-01,2026-10-24,2000,qfq',
 'tx_snapshot': 'https://qt.gtimg.cn/q=sh600519,sz000001,sh000300',
}
for name, u in urls.items():
    t=time.time()
    try:
        r=s.get(u,headers=h,timeout=15)
        print(name, r.status_code, round(time.time()-t,2), len(r.text), r.text[:160].replace('\n',' '))
    except Exception as e:
        print(name, 'ERR', type(e).__name__, e)
