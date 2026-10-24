import akshare as ak, time
inds=ak.stock_board_industry_name_ths(); print(inds.shape, inds.head(3).to_dict('records'))
for name in ['半导体','银行','白酒']:
    t=time.time()
    try:
        df=ak.stock_board_industry_index_ths(symbol=name,start_date='2019-01-01',end_date='2026-10-24')
        print(name, df.shape, round(time.time()-t,2), df.columns.tolist(), df.head(2).to_dict('records'), df.tail(1).to_dict('records'))
    except Exception as e:
        print(name,'ERR',type(e).__name__,e)
