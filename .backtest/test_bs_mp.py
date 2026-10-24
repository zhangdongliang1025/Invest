import baostock as bs, time, sys
from concurrent.futures import ProcessPoolExecutor

def worker(args):
    tag, codes = args
    lg=bs.login()
    out=[]
    t=time.time()
    for c in codes:
        rs=bs.query_history_k_data_plus(c,'date,close',start_date='2022-08-01',end_date='2026-10-24',frequency='d',adjustflag='2')
        n=0
        while rs.error_code=='0' and rs.next(): rs.get_row_data(); n+=1
        out.append((c,n))
    bs.logout()
    return tag, round(time.time()-t,2), lg.error_code, out

if __name__=='__main__':
    codes=['sh.600519','sz.000001','sz.300750','sh.601318','sz.000002','sh.600036','sz.000858','sh.601888','sz.002594','sh.688981']
    with ProcessPoolExecutor(max_workers=2) as ex:
        for r in ex.map(worker, [('A',codes),('B',codes)]):
            print(r[0],r[1],r[2],r[3])
