"""U07 涨跌家数极值回测：全 A 宽度 -> 沪深300 未来 5/10/20 日收益。"""
import pandas as pd, numpy as np, glob, os, json, gzip
from concurrent.futures import ThreadPoolExecutor
import importlib.util

BASE = os.path.dirname(__file__)
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)
COST = 0.0005  # 指数/ETF 单边 0.05%，往返 0.1%（仅作参考，收益为指数口径）


def load_panel():
    files = glob.glob(os.path.join(BASE, "data", "sina_stocks", "*.csv.gz"))

    def one(f):
        sym = os.path.basename(f).replace(".csv.gz", "")
        d = pd.read_csv(f, usecols=["date", "close", "amount"])
        d["sym"] = sym
        return d

    with ThreadPoolExecutor(max_workers=16) as ex:
        frames = list(ex.map(one, files))
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    close = df.pivot(index="date", columns="sym", values="close").sort_index()
    amount = df.pivot(index="date", columns="sym", values="amount").sort_index()
    return close, amount, len(files)


def load_hs300():
    h = pd.read_csv(os.path.join(BASE, "data", "hs300.csv"), parse_dates=["date"])
    h = h.sort_values("date").set_index("date")
    for c in ["open", "close"]:
        h[c] = pd.to_numeric(h[c], errors="coerce")
    return h


def forward_ret(hs, n):
    dates = list(hs.index)
    pos = {d: i for i, d in enumerate(dates)}
    out = pd.Series(np.nan, index=hs.index, dtype=float)
    for t in dates:
        i = pos[t]
        if i + n >= len(dates):
            continue
        d1, dn = dates[i + 1], dates[i + n]
        o, c = hs.at[d1, "open"], hs.at[dn, "close"]
        if pd.notna(o) and pd.notna(c) and o > 0:
            out.at[t] = c / o - 1
    return out


def desc(v, label):
    v = pd.Series(v).dropna()
    n = len(v)
    if n == 0:
        return {"label": label, "n": 0}
    mean = float(v.mean()); std = float(v.std(ddof=1)) if n > 1 else np.nan
    return {"label": label, "n": int(n), "mean": mean, "median": float(v.median()),
            "win_pos": float((v > 0).mean()), "std": std,
            "t": float(mean / (std / np.sqrt(n))) if n > 1 and std > 0 else None,
            "min": float(v.min()), "max": float(v.max())}


def dedup(mask, cooldown=20):
    m = mask.fillna(False).to_numpy().copy()
    last = -10**9
    for i, v in enumerate(m):
        if v and i - last >= cooldown:
            last = i
        elif v:
            m[i] = False
    return pd.Series(m, index=mask.index)


def welch(a, b):
    a = pd.Series(a).dropna(); b = pd.Series(b).dropna()
    if len(a) < 2 or len(b) < 2:
        return None
    va, vb = a.var(ddof=1), b.var(ddof=1)
    se = np.sqrt(va / len(a) + vb / len(b))
    return float((a.mean() - b.mean()) / se) if se > 0 else None


def main():
    close, amount, nfiles = load_panel()
    hs = load_hs300()
    common = close.index.intersection(hs.index)
    close, amount, hs = close.loc[common], amount.loc[common], hs.loc[common]
    # 只用有成交额的交易日；剔除上市前 5 个交易日
    obs = close.notna().cumsum()
    valid = close.notna() & close.shift(1).notna() & (obs > 5) & (amount > 1e6)
    # 有效个股足够多的交易日才是可计算样本（新浪个股数据起点约 2022-08）
    day_valid = valid.sum(axis=1)
    keep = day_valid >= 1000
    close, amount, hs = close.loc[keep], amount.loc[keep], hs.loc[keep]
    valid = valid.loc[keep]
    ret = close.pct_change()
    up = (ret > 0) & valid
    dn = (ret < 0) & valid
    adv = up.sum(axis=1).astype(int)
    dec = dn.sum(axis=1).astype(int)
    total = adv + dec
    breadth = adv / total.replace(0, np.nan)
    net = (adv - dec) / total.replace(0, np.nan)
    fwd = {n: forward_ret(hs, n) for n in (5, 10, 20)}
    fwd_net = {n: fwd[n] - COST * 2 for n in fwd}

    split = pd.Timestamp("2025-01-01")
    pct = breadth.rolling(750, min_periods=250).rank(pct=True)

    # 市场状态：信号日前 20 日沪深300 涨幅（用于区分牛熊状态下的宽度极值）
    mom20 = hs["close"].pct_change(20).shift(1)

    results = {"sample": {"start": str(common[0].date()), "end": str(common[-1].date()),
                          "data_start": str(close.index[0].date()), "data_end": str(close.index[-1].date()),
                          "days": int(len(close)), "stocks_loaded": int(nfiles),
                          "avg_valid_stocks": float(day_valid[keep].mean()),
                          "min_valid": int(day_valid[keep].min()),
                          "max_valid": int(day_valid[keep].max())},
               "unconditional": {}, "unconditional_full_index": {}, "signals": {}}

    for n in (5, 10, 20):
        results["unconditional"][str(n)] = desc(fwd_net[n], f"uncond {n}")
        results["unconditional_full_index"][str(n)] = desc(forward_ret(hs.loc[close.index[0]:], n), f"uncond_full {n}")

    # 绝对家数（源口径）与百分比口径
    defs = {
        "abs_adv_3240": adv >= 3240,
        "abs_adv_360": adv <= 360,
        "pct_adv_85": breadth >= 0.85,
        "pct_adv_90": breadth >= 0.90,
        "pct_dec_15": breadth <= 0.15,
        "pct_dec_10": breadth <= 0.10,
        "pct_src_926": breadth >= 3240 / 3500,
        "pct_src_103": breadth <= 360 / 3500,
        "roll_pct_high": pct >= 0.95,
        "roll_pct_low": pct <= 0.05,
    }

    def eval_mask(raw_mask, label):
        m = dedup(raw_mask, 20)
        out = {"label": label, "raw_days": int(raw_mask.sum()), "events_dedup": int(m.sum()),
               "horizons": {}}
        for n in (5, 10, 20):
            vals = fwd_net[n][m]
            dates = vals.index
            out["horizons"][str(n)] = {
                "all": desc(vals, f"{label} {n}"),
                "is": desc(vals[dates < split], f"{label} {n} IS"),
                "oos": desc(vals[dates >= split], f"{label} {n} OOS"),
                "vs_uncond_t": welch(vals, fwd_net[n]),
            }
        # 市场状态拆分（信号前 20 日指数涨跌）
        v20 = fwd_net[20][m]
        reg = mom20.reindex(v20.index)
        out["regime_20d"] = {
            "bull": desc(v20[reg > 0], f"{label} bull"),
            "bear": desc(v20[reg <= 0], f"{label} bear"),
        }
        ev = m[m].index
        out["event_dates"] = [str(d.date()) for d in ev]
        return out

    for k, mask in defs.items():
        results["signals"][k] = eval_mask(mask, k)

    # 宽度分档（当日宽度 -> 未来 20 日收益），按日等权，避免阈值选择
    bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    q = pd.DataFrame({"breadth": breadth, "fwd20": fwd_net[20]}).dropna()
    q["bucket"] = pd.cut(q["breadth"], bins=bins, include_lowest=True)
    tab = q.groupby("bucket", observed=True)["fwd20"].agg(["count", "mean", "median",
                                                           lambda x: (x > 0).mean()])
    tab.columns = ["count", "mean", "median", "win_pos"]
    results["breadth_bucket_20d"] = {str(k): {"count": int(v["count"]), "mean": float(v["mean"]),
                                              "median": float(v["median"]),
                                              "win_pos": float(v["win_pos"])}
                                     for k, v in tab.iterrows()}

    # 年度分布
    hi = dedup(breadth >= 0.85, 20)
    lo = dedup(breadth <= 0.15, 20)
    results["extreme_years"] = {
        "high": {int(y): int(v) for y, v in pd.Series(hi[hi].index.year).value_counts().sort_index().items()},
        "low": {int(y): int(v) for y, v in pd.Series(lo[lo].index.year).value_counts().sort_index().items()},
    }

    with open(os.path.join(OUT, "u07_results.json"), "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    # 事件明细
    rows = []
    for k in ("pct_adv_85", "pct_dec_15", "abs_adv_3240", "abs_adv_360"):
        m = dedup(defs[k], 20)
        for d in m[m].index:
            rows.append({"date": str(d.date()), "type": k, "adv": int(adv[d]), "dec": int(dec[d]),
                         "breadth": float(breadth[d]), "fwd5": float(fwd_net[5].get(d, np.nan)),
                         "fwd10": float(fwd_net[10].get(d, np.nan)), "fwd20": float(fwd_net[20].get(d, np.nan))})
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "u07_events.csv"), index=False)

    # 宽度序列校验：典型区间 + 历史关键时点
    results["breadth_stats"] = {
        "mean": float(breadth.mean()), "median": float(breadth.median()),
        "p05": float(breadth.quantile(0.05)), "p95": float(breadth.quantile(0.95)),
        "min": float(breadth.min()), "max": float(breadth.max()),
        "min_date": str(breadth.idxmin().date()), "max_date": str(breadth.idxmax().date()),
    }
    probes = ["2024-02-05", "2024-02-06", "2024-09-30", "2024-10-08", "2025-01-14",
              "2025-02-19", "2022-10-11", "2023-01-03", "2022-04-25", "2022-04-29"]
    results["breadth_probes"] = {}
    for p in probes:
        d = pd.Timestamp(p)
        if d in breadth.index:
            results["breadth_probes"][p] = {"adv": int(adv[d]), "dec": int(dec[d]),
                                            "breadth": float(breadth[d])}

    with open(os.path.join(OUT, "u07_results.json"), "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str)[:18000])


if __name__ == "__main__":
    main()
