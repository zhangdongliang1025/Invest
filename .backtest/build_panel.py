"""构建全 A 日线面板缓存（新浪前复权），供 U03/U06 回测复用。"""
import pandas as pd, numpy as np, glob, os, pickle
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(__file__)
DATA = os.path.join(BASE, "data")
CACHE = os.path.join(DATA, "panel_cache.pkl")


def main():
    files = glob.glob(os.path.join(DATA, "sina_stocks", "*.csv.gz"))

    def one(f):
        sym = os.path.basename(f).replace(".csv.gz", "")
        d = pd.read_csv(f, usecols=["date", "open", "high", "low", "close", "amount"])
        d["sym"] = sym
        return d

    with ThreadPoolExecutor(max_workers=16) as ex:
        frames = list(ex.map(one, files))
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["date", "sym"], keep="last")
    mats = {}
    for col in ["open", "high", "low", "close", "amount"]:
        mats[col] = df.pivot(index="date", columns="sym", values=col).sort_index().sort_index(axis=1)
    # 名称与 ST 标记
    names = {}
    try:
        import akshare as ak
        info = ak.stock_info_a_code_name()
        for c, n in zip(info["code"].astype(str), info["name"].astype(str)):
            sym = ("sh" if c.startswith(("60", "68")) else "sz") + c
            names[sym] = n
    except Exception as e:
        print("name load failed:", e)
    with open(CACHE, "wb") as f:
        pickle.dump({"mats": mats, "names": names}, f, protocol=4)
    print("dates", mats["close"].shape[0], "symbols", mats["close"].shape[1],
          "range", mats["close"].index[0].date(), mats["close"].index[-1].date())


if __name__ == "__main__":
    main()
