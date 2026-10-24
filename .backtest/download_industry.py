"""下载 90 个同花顺行业指数（2019-2026，含成交额）与沪深300指数日线。"""
import akshare as ak
import pandas as pd
import os, time

OUT = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(os.path.join(OUT, "industry"), exist_ok=True)
START, END = "2019-01-01", "2026-10-24"

inds = ak.stock_board_industry_name_ths()
print("industries", len(inds), flush=True)
fail = []
for i, row in inds.iterrows():
    name, code = row["name"], str(row["code"])
    path = os.path.join(OUT, "industry", f"{code}.csv")
    if os.path.exists(path) and os.path.getsize(path) > 100:
        continue
    for attempt in range(3):
        try:
            df = ak.stock_board_industry_index_ths(symbol=name, start_date=START, end_date=END)
            if df is None or len(df) < 100:
                raise ValueError(f"too few rows: {0 if df is None else len(df)}")
            df = df.rename(columns={"日期": "date", "开盘价": "open", "最高价": "high",
                                    "最低价": "low", "收盘价": "close", "成交量": "volume",
                                    "成交额": "amount"})
            df.insert(0, "code", code)
            df.insert(1, "name", name)
            df.to_csv(path, index=False)
            break
        except Exception as e:
            if attempt == 2:
                fail.append((code, name, f"{type(e).__name__}: {e}"))
                print("FAIL", code, name, e, flush=True)
            else:
                time.sleep(1 + attempt)
    if (i + 1) % 10 == 0:
        print(f"{i+1}/{len(inds)}", flush=True)

# 沪深300 指数：用 baostock（指数无复权问题）
import baostock as bs
lg = bs.login()
rs = bs.query_history_k_data_plus("sh.000300", "date,open,high,low,close,volume,amount",
                                  start_date=START, end_date=END, frequency="d")
rows = []
while rs.error_code == "0" and rs.next():
    rows.append(rs.get_row_data())
bs.logout()
idx = pd.DataFrame(rows, columns=rs.fields)
idx.to_csv(os.path.join(OUT, "hs300.csv"), index=False)
print("hs300", idx.shape, flush=True)
print("failures", fail, flush=True)
