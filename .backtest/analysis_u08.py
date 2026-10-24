"""U08 行业拥挤度回测：成交额占比分位/偏离度 -> 未来 20 日相对沪深300 超额。"""
import pandas as pd, numpy as np, glob, os, json

BASE = os.path.dirname(__file__)
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)
COST = 0.001  # 单边 0.1%（ETF 佣金+滑点），往返 0.2%


def load_industry():
    frames = []
    for f in glob.glob(os.path.join(BASE, "data", "industry", "*.csv")):
        d = pd.read_csv(f, parse_dates=["date"])
        frames.append(d[["date", "code", "name", "open", "close", "amount"]])
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values(["date", "code"])
    amt = df.pivot(index="date", columns="code", values="amount").sort_index()
    close = df.pivot(index="date", columns="code", values="close").sort_index()
    open_ = df.pivot(index="date", columns="code", values="open").sort_index()
    names = df.drop_duplicates("code").set_index("code")["name"].to_dict()
    # 只保留覆盖率足够的日期
    ok = amt.notna().sum(axis=1) >= 80
    return amt.loc[ok], close.loc[ok], open_.loc[ok], names


def load_hs300():
    h = pd.read_csv(os.path.join(BASE, "data", "hs300.csv"), parse_dates=["date"])
    h = h.sort_values("date").set_index("date")
    for c in ["open", "close"]:
        h[c] = pd.to_numeric(h[c], errors="coerce")
    return h


def forward_excess(close, open_, hs, n):
    """信号日 t 收盘确认，t+1 开盘入场，t+n 收盘出场。"""
    idx = close.index
    dates = list(idx)
    pos = {d: i for i, d in enumerate(dates)}
    fwd = pd.DataFrame(np.nan, index=idx, columns=close.columns)
    hs_fwd = pd.Series(np.nan, index=idx)
    for t in dates:
        i = pos[t]
        if i + n >= len(dates):
            continue
        d1, dn = dates[i + 1], dates[i + n]
        if d1 not in hs.index or dn not in hs.index:
            continue
        h0, h1 = hs.at[d1, "open"], hs.at[dn, "close"]
        if pd.notna(h0) and pd.notna(h1) and h0 > 0:
            hs_fwd.at[t] = h1 / h0 - 1
            o1 = open_.loc[d1]
            cn = close.loc[dn]
            fwd.loc[t] = cn / o1 - 1
    return fwd.sub(hs_fwd, axis=0), fwd, hs_fwd


def dedup_events(mask, cooldown=20):
    """按行业去重：同一行业信号后 cooldown 个交易日内不重复计。"""
    out = mask.copy()
    for col in mask.columns:
        s = mask[col].fillna(False).to_numpy()
        last = -10**9
        for i, v in enumerate(s):
            if v and i - last >= cooldown:
                last = i
            elif v:
                out.iloc[i, out.columns.get_loc(col)] = False
    return out


def stats(values, label):
    v = pd.Series(values).dropna()
    n = len(v)
    if n == 0:
        return {"label": label, "n": 0}
    mean = float(v.mean())
    std = float(v.std(ddof=1)) if n > 1 else np.nan
    t = mean / (std / np.sqrt(n)) if n > 1 and std > 0 else np.nan
    return {"label": label, "n": int(n), "mean": mean, "median": float(v.median()),
            "win_neg": float((v < 0).mean()), "std": std, "t": float(t) if pd.notna(t) else None,
            "min": float(v.min()), "max": float(v.max())}


def main():
    amt, close, open_, names = load_industry()
    hs = load_hs300()
    # 对齐到共同交易日
    common = amt.index.intersection(close.index).intersection(open_.index).intersection(hs.index)
    amt, close, open_, hs = amt.loc[common], close.loc[common], open_.loc[common], hs.loc[common]

    mkt = amt.sum(axis=1)
    ratio = amt.div(mkt, axis=0) * 100
    ma120 = ratio.rolling(120, min_periods=60).mean()
    score = (ratio - ma120) / ma120 * 100
    pct = ratio.rolling(750, min_periods=250).rank(pct=True)
    pct_strict = ratio.rolling(750, min_periods=750).rank(pct=True)

    fwd = {}
    raw = {}
    hsret = {}
    for n in (5, 10, 20):
        fwd[n], raw[n], hsret[n] = forward_excess(close, open_, hs, n)
        # 扣除往返成本（多头行业 + 空/基准不减仓；这里只扣行业 ETF 往返）
        fwd[n] = fwd[n] - COST * 2

    split = pd.Timestamp("2023-01-01")
    results = {"sample": {"start": str(common[0].date()), "end": str(common[-1].date()),
                          "days": int(len(common)), "industries": int(ratio.shape[1]),
                          "cost_roundtrip": COST * 2}}

    def eval_mask(mask, label):
        mask = dedup_events(mask)
        out = {"label": label, "events": int(mask.sum().sum()),
               "per_horizon": {}}
        for n in (5, 10, 20):
            vals = fwd[n].where(mask).stack()
            dates = pd.Series(vals.index.get_level_values(0), index=vals.index)
            out["per_horizon"][str(n)] = {
                "all": stats(vals, f"{label} all"),
                "is": stats(vals[dates < split], f"{label} IS"),
                "oos": stats(vals[dates >= split], f"{label} OOS"),
            }
        # 事件按年
        vals20 = fwd[20].where(mask).stack()
        yrs = pd.Series(vals20.index.get_level_values(0).year, index=vals20.index)
        out["by_year_20"] = {int(y): stats(vals20[yrs == y], f"{label} {y}") for y in sorted(yrs.unique())}
        # 事件行业分布
        ev = mask.sum().sort_values(ascending=False)
        out["top_industries"] = [{"code": str(c), "name": names.get(c, ""), "events": int(v)}
                                 for c, v in ev.head(10).items() if v > 0]
        return out

    results["signals"] = {
        "pct95": eval_mask(pct > 0.95, "RATIO_PCT_3Y>95%"),
        "pct90": eval_mask(pct > 0.90, "RATIO_PCT_3Y>90%"),
        "score300": eval_mask(score > 300, "RATIO_SCORE>300"),
        "score100": eval_mask(score > 100, "RATIO_SCORE>100"),
        "pct95_strict": eval_mask(pct_strict > 0.95, "RATIO_PCT_3Y>95% (需3年历史)"),
    }

    # 阈值敏感性（20 日）
    th = []
    for s in (50, 100, 150, 200, 250, 300, 400, 500):
        m = dedup_events(score > s)
        vals = fwd[20].where(m).stack()
        st = stats(vals, f"score>{s}")
        st["threshold"] = s
        th.append(st)
    for p in (0.90, 0.95, 0.98, 0.99):
        m = dedup_events(pct > p)
        vals = fwd[20].where(m).stack()
        st = stats(vals, f"pct>{p}")
        st["threshold"] = p
        th.append(st)
    results["threshold_table_20d"] = th

    # score>300 事件明细 + 按日聚集 bootstrap
    m300 = dedup_events(score > 300)
    ev_rows = []
    for d in m300.index:
        cols = m300.columns[m300.loc[d].fillna(False)]
        for c in cols:
            ev_rows.append({"date": str(d.date()), "code": str(c), "name": names.get(c, ""),
                            "score": float(score.at[d, c]), "ratio": float(ratio.at[d, c]),
                            "ind_ret20": float(raw[20].at[d, c]) if pd.notna(raw[20].at[d, c]) else None,
                            "hs_ret20": float(hsret[20].at[d]) if pd.notna(hsret[20].at[d]) else None,
                            "excess20": float(fwd[20].at[d, c]) if pd.notna(fwd[20].at[d, c]) else None})
    ev = pd.DataFrame(ev_rows)
    if len(ev):
        ev.to_csv(os.path.join(OUT, "u08_events_score300.csv"), index=False)
        by_date = ev.dropna(subset=["excess20"]).groupby("date")["excess20"].mean()
        rng = np.random.default_rng(42)
        boot = [float(by_date.sample(len(by_date), replace=True, random_state=int(rng.integers(1e9))).mean())
                for _ in range(5000)]
        results["score300_date_cluster"] = {
            "unique_dates": int(len(by_date)),
            "mean_of_date_means": float(by_date.mean()),
            "ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
            "years": {int(y): int(v) for y, v in ev["date"].str[:4].value_counts().sort_index().items()},
        }


    # 无条件基准：全部行业日 + 每 20 日非重叠抽样
    for n in (5, 10, 20):
        allv = fwd[n].stack()
        results.setdefault("unconditional", {})[str(n)] = stats(allv, f"uncond {n}")
    # 非重叠：每个行业从第 0 天起每 20 个交易日取一次
    mask = pd.DataFrame(False, index=ratio.index, columns=ratio.columns)
    for j, c in enumerate(ratio.columns):
        mask.iloc[::20, j] = True
    results["unconditional_nonoverlap_20"] = stats(fwd[20].where(mask).stack(), "uncond 20 nonoverlap")

    # 横截面分位 -> 未来 20 日超额（按日等权，避免事件选择偏差）
    q = pct.stack().rename("pct").to_frame()
    q["fwd20"] = fwd[20].stack()
    q = q.dropna()
    q["bucket"] = pd.cut(q["pct"], bins=np.arange(0, 1.01, 0.1), include_lowest=True)
    qtab = q.groupby("bucket", observed=True)["fwd20"].agg(["count", "mean", "median",
                                                             lambda x: (x < 0).mean()])
    qtab.columns = ["count", "mean", "median", "win_neg"]
    results["cross_section_decile"] = {str(k): {"count": int(v["count"]), "mean": float(v["mean"]),
                                                "median": float(v["median"]), "win_neg": float(v["win_neg"])}
                                       for k, v in qtab.iterrows()}

    # 状态：信号日的市场状态（用于解释）
    results["signal_dates"] = []
    for label, mask in [("pct95", pct > 0.95), ("score300", score > 300)]:
        m = dedup_events(mask)
        for d in m.index[m.sum(axis=1) > 0]:
            results["signal_dates"].append({"date": str(d.date()), "type": label,
                                            "industries": int(m.loc[d].sum())})

    with open(os.path.join(OUT, "u08_results.json"), "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    # 打印摘要
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str)[:20000])


if __name__ == "__main__":
    main()
