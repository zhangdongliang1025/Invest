import baostock as bs, time
bs.login()
for code in ['sh.600519','sz.000001','sz.300750','sh.601318','sz.000002']:
    t=time.time(); rs=bs.query_history_k_data_plus(code,'date,close',start_date='2022-08-01',end_date='2026-10-24',frequency='d',adjustflag='2')
    n=0
    while rs.error_code=='0' and rs.next(): rs.get_row_data(); n+=1
    print(code,n,round(time.time()-t,3))
bs.logout()
