"""全 A（含 2022-08 后退市）新浪日线 + 前复权因子，按股票落盘，支持断点续传。"""
import requests, json, re, os, gzip, time, sys, random
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = os.path.dirname(__file__)
OUT = os.path.join(BASE, "data", "sina_stocks")
os.makedirs(OUT, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0"}
START = "2022-08-01"  # 新浪最多 1023 根，约 4.2 年


def universe():
    import akshare as ak
    df = ak.stock_info_a_code_name()
    syms = set()
    for c in df["code"].astype(str):
        if c.startswith(("60", "68")):
            syms.add("sh" + c)
        elif c.startswith(("00", "30")):
            syms.add("sz" + c)
    # 退市股：补足 2022-08 之后退市的样本，降低生存偏差
    try:
        sh = ak.stock_info_sh_delist()
        sh = sh[sh["暂停上市日期"] >= pd.Timestamp(START).date()]
        for c in sh["公司代码"].astype(str):
            if c.startswith(("60", "68")):
                syms.add("sh" + c)
        sz = ak.stock_info_sz_delist()
        sz = sz[sz["终止上市日期"] >= pd.Timestamp(START).date()]
        for c in sz["证券代码"].astype(str):
            if c.startswith(("00", "30")):
                syms.add("sz" + c)
    except Exception as e:
        print("delisted list failed:", e, flush=True)
    return sorted(syms)


def parse_qfq(text, sym):
    i = text.find("{")
    if i < 0:
        return []
    try:
        obj, _ = json.JSONDecoder().raw_decode(text, i)
    except Exception:
        return []
    out = []
    for it in obj.get("data", []):
        try:
            out.append((it["d"], float(it["f"])))
        except Exception:
            pass
    out.sort()
    return out


def adjust(rows, factors):
    """rows: list of (date, open, high, low, close, volume). 前复权：raw/f，f 取最近一次除权事件。"""
    if not factors:
        factors = [("1900-01-01", 1.0)]
    fd = [x[0] for x in factors]
    fv = [x[1] for x in factors]
    # 日期 <= t 的最后一个因子；早于首个事件则用首个事件的因子
    out = []
    import bisect
    for d, o, hi, lo, c, v in rows:
        i = bisect.bisect_right(fd, d) - 1
        if i < 0:
            i = 0
        f = fv[i]
        if f <= 0:
            f = 1.0
        out.append((d, o / f, hi / f, lo / f, c / f, v, c, v * c))
    return out


def fetch(sym):
    path = os.path.join(OUT, sym + ".csv.gz")
    if os.path.exists(path) and os.path.getsize(path) > 50:
        return sym, "skip", 0
    u = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
         f"CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=1023")
    last = None
    for attempt in range(3):
        try:
            r = requests.get(u, headers=H, timeout=20)
            r.raise_for_status()
            arr = r.json()
            if not isinstance(arr, list) or not arr:
                return sym, "empty", 0
            rows = []
            for x in arr:
                try:
                    rows.append((x["day"], float(x["open"]), float(x["high"]),
                                 float(x["low"]), float(x["close"]), float(x["volume"])))
                except Exception:
                    continue
            if len(rows) < 20:
                return sym, "short", len(rows)
            q = (f"https://finance.sina.com.cn/realstock/company/{sym}/qfq.js")
            try:
                rq = requests.get(q, headers=H, timeout=15)
                factors = parse_qfq(rq.text, sym) if rq.status_code == 200 else []
            except Exception:
                factors = []
            adj = adjust(rows, factors)
            with gzip.open(path, "wt", newline="") as f:
                f.write("date,open,high,low,close,volume,raw_close,amount\n")
                for d, o, hi, lo, c, v, rc, amt in adj:
                    f.write(f"{d},{o:.4f},{hi:.4f},{lo:.4f},{c:.4f},{v:.0f},{rc:.4f},{amt:.2f}\n")
            return sym, "ok", len(adj)
        except Exception as e:
            last = f"{type(e).__name__}:{e}"
            time.sleep(0.5 + attempt)
    return sym, "ERR:" + str(last), 0


def main(n=24, limit=None):
    syms = universe()
    if limit:
        random.seed(7); syms = random.sample(syms, min(limit, len(syms)))
    print(f"universe={len(syms)} workers={n}", flush=True)
    t0 = time.time(); done = ok = empty = err = 0
    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = [ex.submit(fetch, s) for s in syms]
        for i, f in enumerate(as_completed(futs), 1):
            sym, st, cnt = f.result()
            done += 1
            if st == "ok": ok += 1
            elif st == "skip": pass
            elif st.startswith("ERR"): err += 1
            else: empty += 1
            if i % 200 == 0 or i == len(syms):
                el = time.time() - t0
                print(f"{i}/{len(syms)} ok={ok} err={err} empty={empty} {el:.0f}s "
                      f"{i/el:.2f}/s", flush=True)
    print(f"FINISHED ok={ok} err={err} empty={empty} {time.time()-t0:.0f}s", flush=True)
    if err:
        print("rerun to retry failures", flush=True)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    main(n, limit)
