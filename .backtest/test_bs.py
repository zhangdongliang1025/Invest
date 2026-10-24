import baostock as bs, time
lg=bs.login(); print('login', lg.error_code, lg.error_msg)
t=time.time()
rs=bs.query_history_k_data_plus('sh.600519','date,code,open,high,low,close,volume,amount,turn',start_date='2019-01-01',end_date='2026-10-24',frequency='d',adjustflag='2')
rows=[]
while (rs.error_code=='0') and rs.next(): rows.append(rs.get_row_data())
print('rows',len(rows),'sec',round(time.time()-t,2), rows[0][:6] if rows else None, rows[-1][:6] if rows else None)
bs.logout()
