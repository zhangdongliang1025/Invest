"""全 A 前复权日线下载（baostock，含退市股），按股票落盘，支持断点续传。"""
import baostock as bs
import pandas as pd
import os, sys, time, gzip, json
from multiprocessing import Process

START = "2019-01-01"
END = "2026-10-24"
OUT = os.path.join(os.path.dirname(__file__), "data", "stocks")
FIELDS = "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg,tradestatus,isST"


def universe():
    lg = bs.login()
    assert lg.error_code == "0", lg.error_msg
    rs = bs.query_stock_basic()
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    bs.logout()
    df = pd.DataFrame(rows, columns=rs.fields)
    df = df[(df["type"] == "1") & (df["code"].str.startswith(("sh.", "sz.")))]
    df = df[df["ipoDate"] <= END]
    df = df[(df["outDate"] == "") | (df["outDate"] >= START)]
    return sorted(df["code"].unique())


def worker(shard_id, codes):
    os.makedirs(OUT, exist_ok=True)
    lg = bs.login()
    if lg.error_code != "0":
        print(f"[shard {shard_id}] login failed: {lg.error_msg}", flush=True)
        return
    t0 = time.time()
    done = skipped = empty = 0
    for i, code in enumerate(codes):
        path = os.path.join(OUT, code.replace(".", "_") + ".csv.gz")
        if os.path.exists(path) and os.path.getsize(path) > 50:
            skipped += 1
            continue
        try:
            rs = bs.query_history_k_data_plus(
                code, FIELDS, start_date=START, end_date=END,
                frequency="d", adjustflag="2")
            rows = []
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
        except Exception as e:
            print(f"[shard {shard_id}] ERR {code} {type(e).__name__}: {e}", flush=True)
            continue
        if rows:
            with gzip.open(path, "wt", newline="") as f:
                f.write(",".join(rs.fields) + "\n")
                for r in rows:
                    f.write(",".join(r) + "\n")
            done += 1
        else:
            empty += 1
        if (i + 1) % 100 == 0:
            el = time.time() - t0
            print(f"[shard {shard_id}] {i+1}/{len(codes)} done={done} skip={skipped} "
                  f"empty={empty} {el:.0f}s {((i+1)/el):.2f}/s", flush=True)
    bs.logout()
    print(f"[shard {shard_id}] FINISHED done={done} skip={skipped} empty={empty} "
          f"{time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    codes = universe()
    print(f"universe={len(codes)} shards={n}", flush=True)
    # 交错分片，避免按代码段集中（退市/板块偏差）
    shards = [codes[i::n] for i in range(n)]
    procs = [Process(target=worker, args=(i, s)) for i, s in enumerate(shards)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    print("ALL FINISHED", flush=True)
