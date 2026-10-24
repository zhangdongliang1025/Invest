"""U03（波段/均线）与 U06（盈亏比/止损）回测：全 A 面板，前复权日线。"""
import pandas as pd, numpy as np, pickle, os, json

BASE = os.path.dirname(__file__)
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

COST_BUY = 0.0013       # 佣金 0.03% + 滑点 0.10%
COST_SELL = 0.0018      # 佣金 0.03% + 印花税 0.05% + 滑点 0.10%
COST_STRESS = (0.0028, 0.0035)
MIN_AMOUNT20 = 1e8      # 20 日均成交额 ≥ 1 亿
MIN_OBS = 120           # 至少 120 个交易日历史
SLOT = 10               # 最大持仓数
SPLIT = pd.Timestamp("2025-01-01")
SIGNAL_COOLDOWN = 5     # 同股信号冷却（交易日）
HORIZONS = (5, 10, 20, 60)


def load():
    with open(os.path.join(BASE, "data", "panel_cache.pkl"), "rb") as f:
        d = pickle.load(f)
    mats = d["mats"]; names = d["names"]
    cnt = mats["close"].notna().sum(axis=1)
    dense = cnt >= 2000
    dates = mats["close"].index[dense]
    syms = mats["close"].columns
    M = {k: mats[k].loc[dates].to_numpy(dtype="float64") for k in ["open", "high", "low", "close", "amount"]}
    M["dates"] = dates; M["syms"] = syms; M["names"] = names
    return M


def indicators(M):
    dates, syms, names = M["dates"], M["syms"], M["names"]
    df = lambda a: pd.DataFrame(a, index=dates, columns=syms)
    c = df(M["close"]); h = df(M["high"]); l = df(M["low"]); amt = df(M["amount"])
    c_ff = c.ffill(limit=5)
    ma5 = c.rolling(5, min_periods=5).mean()
    ma10 = c.rolling(10, min_periods=10).mean()
    ma20 = c.rolling(20, min_periods=20).mean()
    ma60 = c.rolling(60, min_periods=60).mean()
    tradable = amt.notna() & (amt > 0)
    prev_c = c_ff.shift(1)
    hff = h.ffill(limit=5); lff = l.ffill(limit=5)
    tr_vals = np.fmax(np.fmax((hff - lff).to_numpy(), (hff - prev_c).abs().to_numpy()),
                      (lff - prev_c).abs().to_numpy())
    tr = pd.DataFrame(tr_vals, index=dates, columns=syms).where(tradable).ffill(limit=10)
    atr = tr.rolling(14, min_periods=14).mean()
    amt20 = amt.rolling(20, min_periods=20).mean()
    obs = c.notna().cumsum()
    st = np.array([("ST" in str(names.get(s, "")).upper()) or ("退" in str(names.get(s, "")))
                   for s in syms])
    eligible = (tradable & (amt20 >= MIN_AMOUNT20).fillna(False) & (obs > MIN_OBS) & (~st)[None, :])
    universe = (tradable & (amt20 >= 5e7).fillna(False) & (obs > 20) & (~st)[None, :])
    daily_trend = ((c_ff > ma20) & (ma5 > ma10) & (ma10 > ma20) &
                   (ma20 > ma20.shift(10)) & (c_ff > ma60) & (ma60 > ma60.shift(20)))
    pull5 = (l <= ma5 * 1.005) & (c_ff > ma5) & (c_ff > c_ff.shift(1))
    pull10 = (l <= ma10 * 1.005) & (c_ff > ma10) & (c_ff > ma5)
    w = c_ff.resample("W-FRI").last()
    wma = w.rolling(10, min_periods=10).mean()
    w_ok = ((w > wma) & (wma > wma.shift(4))).reindex(dates, method="ffill").fillna(False)
    m = c_ff.resample("ME").last()
    mma = m.rolling(6, min_periods=6).mean()
    m_ok = ((m > mma) & (mma > mma.shift(2))).reindex(dates, method="ffill").fillna(False)
    ret20 = (c_ff / c_ff.shift(20) - 1)
    I = {"ma5": ma5.to_numpy(), "ma10": ma10.to_numpy(), "ma20": ma20.to_numpy(),
         "ma60": ma60.to_numpy(), "atr": atr.to_numpy(), "amt20": amt20.to_numpy(),
         "close_ff": c_ff.to_numpy(), "daily_trend": daily_trend.to_numpy(),
         "pull5": pull5.to_numpy(), "pull10": pull10.to_numpy(),
         "eligible": eligible.to_numpy(), "universe": universe.to_numpy(),
         "tradable": tradable.to_numpy(), "mtf": (w_ok & m_ok).to_numpy(),
         "ret20": ret20.to_numpy()}
    return I


def limit_pct(sym):
    s = str(sym)
    if s.startswith(("sz30", "sh68")):
        return 0.20
    return 0.10


def _scan_exit(o, h, l, c, trad, e, j, stop_raw, target_raw, time_stop, n):
    """返回 (离场日, 离场价(未扣费), 原因)。"""
    for q in range(e + 1, n):
        if not trad[q, j]:
            continue
        if o[q, j] <= stop_raw:
            return q, o[q, j], "gapstop"
        if o[q, j] >= target_raw:
            return q, o[q, j], "gaptarget"
        if l[q, j] <= stop_raw and h[q, j] >= target_raw:
            return q, stop_raw, "stop_first"
        if l[q, j] <= stop_raw:
            return q, stop_raw, "stop"
        if h[q, j] >= target_raw:
            return q, target_raw, "target"
        if q - e >= time_stop:
            return q, c[q, j], "time"
    return n - 1, c[n - 1, j], "end"


def gen_ma_exit_trades(I, M, signal, hard_stop=None, cb=COST_BUY, cs=COST_SELL):
    """信号日收盘确认，次日开盘买入；收盘跌破 MA20 后次日开盘离场。"""
    n, ns = signal.shape
    o, h, l, c = M["open"], M["high"], M["low"], M["close"]
    ma20, elig, trad = I["ma20"], I["eligible"], I["tradable"]
    trades = []
    for j in range(ns):
        idx = np.flatnonzero(signal[:, j])
        if len(idx) == 0:
            continue
        lim = limit_pct(M["syms"][j])
        last_sig = -99
        for p in idx:
            if p - last_sig < SIGNAL_COOLDOWN:
                continue
            e = p + 1
            if e >= n:
                break
            if not trad[e, j] or not elig[e, j]:
                continue
            raw_entry = o[e, j]
            if not np.isfinite(raw_entry) or raw_entry <= 0:
                continue
            if raw_entry / c[p, j] - 1 >= lim * 0.97:
                continue
            last_sig = p
            entry = raw_entry * (1 + cb)
            exit_pos, exit_price, reason = None, None, "end"
            for q in range(e + 1, n):
                if not trad[q, j]:
                    continue
                if hard_stop is not None and c[q, j] < entry * (1 - hard_stop):
                    reason = "hardstop"
                elif c[q, j] < ma20[q, j] * 0.995:
                    reason = "ma20"
                else:
                    continue
                x = q + 1
                while x < n and not trad[x, j]:
                    x += 1
                if x >= n:
                    exit_pos, exit_price = n - 1, c[n - 1, j]
                else:
                    exit_pos, exit_price = x, o[x, j]
                break
            if exit_pos is None:
                exit_pos, exit_price, reason = n - 1, c[n - 1, j], "end"
            exit_net = exit_price * (1 - cs)
            trades.append({"sym": M["syms"][j], "sig_pos": p, "entry_pos": e, "exit_pos": exit_pos,
                           "entry": entry, "exit": exit_net, "reason": reason,
                           "ret": exit_net / entry - 1, "days": exit_pos - e,
                           "rank": float(I["ret20"][p, j]) if np.isfinite(I["ret20"][p, j]) else -9})
    return trades


def gen_stop_target_trades(I, M, signal, r_mult=2.0, atr_mult=2.0, max_stop=0.12,
                           min_stop=0.03, time_stop=20, cb=COST_BUY, cs=COST_SELL,
                           fixed_stop=None):
    """信号日收盘确认，次日开盘买入；ATR 止损 + R 倍数止盈。"""
    n, ns = signal.shape
    o, h, l, c = M["open"], M["high"], M["low"], M["close"]
    atr, elig, trad = I["atr"], I["eligible"], I["tradable"]
    trades = []
    for j in range(ns):
        idx = np.flatnonzero(signal[:, j])
        if len(idx) == 0:
            continue
        lim = limit_pct(M["syms"][j])
        last_sig = -99
        for p in idx:
            if p - last_sig < SIGNAL_COOLDOWN:
                continue
            e = p + 1
            if e >= n:
                break
            if not trad[e, j] or not elig[e, j]:
                continue
            raw_entry = o[e, j]
            if not np.isfinite(raw_entry) or raw_entry <= 0:
                continue
            if raw_entry / c[p, j] - 1 >= lim * 0.97:
                continue
            if fixed_stop is not None:
                sd = float(fixed_stop)
            else:
                a = atr[p, j]
                if not np.isfinite(a) or a <= 0:
                    continue
                sd = float(np.clip(atr_mult * a / raw_entry, min_stop, max_stop))
            stop_raw = raw_entry * (1 - sd)
            target_raw = raw_entry * (1 + r_mult * sd)
            last_sig = p
            q, px, reason = _scan_exit(o, h, l, c, trad, e, j, stop_raw, target_raw, time_stop, n)
            entry = raw_entry * (1 + cb)
            exit_net = px * (1 - cs)
            R = (px - raw_entry) / (raw_entry - stop_raw)
            trades.append({"sym": M["syms"][j], "sig_pos": p, "entry_pos": e, "exit_pos": q,
                           "entry": entry, "exit": exit_net, "reason": reason,
                           "ret": exit_net / entry - 1, "R": float(R), "stop_dist": sd,
                           "days": q - e,
                           "rank": float(I["ret20"][p, j]) if np.isfinite(I["ret20"][p, j]) else -9})
    return trades


def random_entry_trades(I, M, n_draws=20000, r_mult=2.0, atr_mult=2.0, max_stop=0.12,
                        min_stop=0.03, time_stop=20, cb=COST_BUY, cs=COST_SELL,
                        fixed_stop=None, seed=2024):
    """对照组：随机入场 + 同样的止损/止盈/时间规则。"""
    rng = np.random.default_rng(seed)
    n = len(M["dates"])
    o, h, l, c = M["open"], M["high"], M["low"], M["close"]
    atr, elig, trad = I["atr"], I["eligible"], I["tradable"]
    trades = []
    for _ in range(n_draws):
        p = int(rng.integers(0, n - 2))
        e = p + 1
        cand = np.flatnonzero(elig[e] & trad[e])
        if len(cand) == 0:
            continue
        j = int(cand[rng.integers(len(cand))])
        raw_entry = o[e, j]
        if not np.isfinite(raw_entry) or raw_entry <= 0:
            continue
        lim = limit_pct(M["syms"][j])
        if raw_entry / c[p, j] - 1 >= lim * 0.97:
            continue
        if fixed_stop is not None:
            sd = float(fixed_stop)
        else:
            a = atr[p, j]
            if not np.isfinite(a) or a <= 0:
                continue
            sd = float(np.clip(atr_mult * a / raw_entry, min_stop, max_stop))
        stop_raw = raw_entry * (1 - sd)
        target_raw = raw_entry * (1 + r_mult * sd)
        q, px, reason = _scan_exit(o, h, l, c, trad, e, j, stop_raw, target_raw, time_stop, n)
        entry = raw_entry * (1 + cb)
        exit_net = px * (1 - cs)
        trades.append({"sym": M["syms"][j], "sig_pos": p, "entry_pos": e, "exit_pos": q,
                       "entry": entry, "exit": exit_net, "reason": reason,
                       "ret": exit_net / entry - 1, "R": float((px - raw_entry) / (raw_entry - stop_raw)),
                       "stop_dist": sd, "days": q - e, "rank": 0.0})
    return trades


def portfolio_from_trades(trades, M, slot=SLOT, frac=0.1, risk=None, rank=True):
    """事件驱动组合模拟：每日收盘盯市。rank=True 时同日信号按 20 日动量降序分配仓位。"""
    n = len(M["dates"])
    c = M["close"]; o = M["open"]
    cash = 1.0
    pos = []
    executed = []
    entries = {}
    for t in trades:
        entries.setdefault(t["entry_pos"], []).append(t)
    for d in entries:
        if rank:
            entries[d].sort(key=lambda t: -t.get("rank", 0.0))
        else:
            entries[d].sort(key=lambda t: t["sym"])
    eq = np.zeros(n); exposures = np.zeros(n)
    for d in range(n):
        keep = []
        for p in pos:
            if p["exit_pos"] == d:
                cash += p["shares"] * p["exit_price"]
            else:
                keep.append(p)
        pos = keep
        for t in entries.get(d, []):
            if len(pos) >= slot:
                break
            j = t["j"]
            px = o[d, j]
            if not np.isfinite(px) or px <= 0:
                continue
            if risk is None:
                val = cash * frac
            else:
                sd = max(t.get("stop_dist", 0.08), 1e-6)
                val = min(cash * frac, cash * risk / sd)
            shares = val / t["entry"]
            need = shares * t["entry"]
            if shares <= 0 or need > cash * 1.0001:
                continue
            cash -= shares * t["entry"]
            pos.append({"sym": t["sym"], "j": j, "exit_pos": t["exit_pos"],
                        "shares": shares, "entry_price": t["entry"], "exit_price": t["exit"]})
            executed.append(t)
        val = cash
        for p in pos:
            px = c[d, p["j"]]
            if not np.isfinite(px):
                px = p["entry_price"]
            val += p["shares"] * px
        eq[d] = val
        exposures[d] = (val - cash) / val if val > 0 else 0
    return eq, exposures, executed


def metrics(eq, dates):
    eq = np.asarray(eq, dtype=float)
    if len(eq) == 0 or not np.isfinite(eq[0]) or eq[0] <= 0:
        return {}
    years = max((dates[-1] - dates[0]).days / 365.25, 1e-9)
    cagr = (eq[-1] / eq[0]) ** (1 / years) - 1
    peak = np.maximum.accumulate(eq)
    mdd = float(np.max(1 - eq / peak))
    rets = np.diff(eq) / eq[:-1]
    vol = float(np.std(rets, ddof=1) * np.sqrt(252)) if len(rets) > 1 else np.nan
    sharpe = float(np.mean(rets) * 252 / vol) if vol and vol > 0 else None
    return {"cagr": float(cagr), "mdd": mdd, "calmar": float(cagr / mdd) if mdd > 0 else None,
            "sharpe": sharpe, "total": float(eq[-1] / eq[0] - 1), "vol": vol,
            "start": str(dates[0].date()), "end": str(dates[-1].date())}


def trade_stats(trades):
    if not trades:
        return {"n": 0}
    r = np.array([t["ret"] for t in trades], dtype=float)
    r = r[np.isfinite(r)]
    if len(r) == 0:
        return {"n": 0}
    win = r[r > 0]; loss = r[r <= 0]
    p = len(win) / len(r)
    avgw = win.mean() if len(win) else 0.0
    avgl = loss.mean() if len(loss) else 0.0
    payoff = (avgw / abs(avgl)) if avgl != 0 else None
    lg = np.log1p(np.clip(r, -0.99, None))
    eq = np.exp(np.cumsum(lg))
    peak = np.maximum.accumulate(eq)
    mdd = float(np.max(1 - eq / peak))
    maxloss = 0; cur = 0
    for x in r:
        if x <= 0:
            cur += 1; maxloss = max(maxloss, cur)
        else:
            cur = 0
    se = r.std(ddof=1) / np.sqrt(len(r)) if len(r) > 1 else np.nan
    out = {"n": int(len(r)), "win_rate": float(p), "avg_win": float(avgw), "avg_loss": float(avgl),
           "payoff": payoff, "expectancy": float(r.mean()),
           "t_expectancy": float(r.mean() / se) if se and np.isfinite(se) and se > 0 else None,
           "pf": float(win.sum() / abs(loss.sum())) if loss.sum() != 0 else None,
           "mdd_trade_seq": mdd, "max_consec_loss": maxloss,
           "avg_days": float(np.mean([t["days"] for t in trades])),
           "median_days": float(np.median([t["days"] for t in trades]))}
    if "R" in trades[0]:
        R = np.array([t["R"] for t in trades], dtype=float)
        R = R[np.isfinite(R)]
        out["mean_R"] = float(R.mean()); out["median_R"] = float(np.median(R))
        out["R_win_rate"] = float((R > 0).mean())
    return out


def bucket_split(trades, dates):
    out = {}
    for label, sel in (("all", lambda d: True),
                       ("is", lambda d: d < SPLIT),
                       ("oos", lambda d: d >= SPLIT)):
        sub = [t for t in trades if sel(dates[t["entry_pos"]])]
        out[label] = trade_stats(sub)
    return out


def bench_hs300(M):
    h = pd.read_csv(os.path.join(BASE, "data", "hs300.csv"), parse_dates=["date"])
    h = h.set_index("date").sort_index().reindex(M["dates"])
    return (h["close"] / h["open"].iloc[0]).to_numpy()


def bench_ew_universe(M, I):
    """等权全市场基准：每月首个交易日再平衡（流动性 + 非 ST）。"""
    c = M["close"]; n = len(M["dates"])
    univ = I["universe"]
    shares = None
    eq = np.zeros(n)
    per = M["dates"].to_period("M")
    rebal = set((np.flatnonzero(per[:-1] != per[1:]) + 1).tolist()) | {0}
    for d in range(n):
        if d in rebal or shares is None:
            px = c[d]
            ok = univ[d] & np.isfinite(px) & (px > 0)
            kk = int(ok.sum())
            if kk == 0:
                continue
            shares = np.where(ok, 1.0 / kk / px, 0.0)
        vals = shares * np.nan_to_num(c[d], nan=0.0)
        eq[d] = vals.sum()
    first = int(np.flatnonzero(eq > 0)[0])
    eq = eq[first:] / eq[first]
    return eq, first


def market_forward_stats(I, M, horizons=HORIZONS):
    """市场中位股的绝对前瞻收益：次日开盘买入、持有 h 日到收盘。用于剥离「市场拖累」。"""
    n = len(M["dates"])
    c = M["close"]; o = M["open"]
    univ = I["universe"]
    out = {}
    for h in horizons:
        vals = []
        for e in range(0, n - h):
            um = univ[e] & np.isfinite(o[e]) & (o[e] > 0) & np.isfinite(c[e + h - 1]) & (c[e + h - 1] > 0)
            uidx = np.flatnonzero(um)
            if len(uidx) == 0:
                continue
            r = c[e + h - 1, uidx] / o[e, uidx] - 1.0
            vals.append(np.median(r))
        v = np.array(vals, dtype=float)
        v = v[np.isfinite(v)]
        out[h] = {"n": int(len(v)), "mean_median_ret": float(v.mean()),
                  "cum_median_path": float(np.prod(1 + v) - 1),
                  "p05": float(np.percentile(v, 5)), "p95": float(np.percentile(v, 95))}
    return out


def signal_forward_stats(I, M, mask, horizons=HORIZONS, cost=COST_BUY + COST_SELL):
    """信号次日开盘买入、持有 h 日到收盘：绝对收益与相对全市场中位数的超额。"""
    n = len(M["dates"])
    c = M["close"]; o = M["open"]
    univ = I["universe"]
    acc = {h: {"all": [], "is": [], "oos": []} for h in horizons}
    acc_abs = {h: {"all": [], "is": [], "oos": []} for h in horizons}
    for p in np.flatnonzero(mask.any(axis=1)):
        e = p + 1
        if e >= n:
            continue
        js = np.flatnonzero(mask[p])
        key = "is" if M["dates"][p] < SPLIT else "oos"
        for h in horizons:
            q = e + h - 1
            if q >= n:
                continue
            um = univ[e] & np.isfinite(o[e]) & (o[e] > 0) & np.isfinite(c[q]) & (c[q] > 0)
            uidx = np.flatnonzero(um)
            if len(uidx) == 0:
                continue
            mkt = np.median(c[q, uidx] / o[e, uidx] - 1.0)
            absr = c[q, js] / o[e, js] - 1.0
            vals = absr - mkt
            vals = vals[np.isfinite(vals)]
            absr = absr[np.isfinite(absr)]
            acc[h]["all"].extend(vals.tolist())
            acc[h][key].extend(vals.tolist())
            acc_abs[h]["all"].extend(absr.tolist())
            acc_abs[h][key].extend(absr.tolist())
    out = {}
    for h in horizons:
        out[h] = {}
        for k in ("all", "is", "oos"):
            v = np.array(acc[h][k], dtype=float)
            v = v[np.isfinite(v)]
            a = np.array(acc_abs[h][k], dtype=float)
            a = a[np.isfinite(a)]
            if len(v) == 0:
                out[h][k] = {"n": 0}
                continue
            se = v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else np.nan
            out[h][k] = {"n": int(len(v)), "excess_mean": float(v.mean()),
                         "excess_mean_net": float(v.mean() - cost),
                         "excess_t": float(v.mean() / se) if se and np.isfinite(se) and se > 0 else None,
                         "excess_win_rate": float((v > 0).mean()),
                         "abs_mean": float(a.mean()), "abs_mean_net": float(a.mean() - cost),
                         "abs_win_rate": float((a > 0).mean())}
    return out


def main():
    M = load()
    I = indicators(M)
    dates = M["dates"]
    sym_idx = {s: i for i, s in enumerate(M["syms"])}
    base = I["daily_trend"] & I["eligible"]
    sig_daily_ma5 = base & I["pull5"]
    sig_daily_ma10 = base & I["pull10"]
    sig_mtf_ma5 = base & I["pull5"] & I["mtf"]
    sig_mtf_ma10 = base & I["pull10"] & I["mtf"]

    n_is = int((np.array(dates) < SPLIT).sum())
    st_flag = np.array([("ST" in str(M["names"].get(s, "")).upper()) or ("退" in str(M["names"].get(s, "")))
                         for s in M["syms"]])
    results = {"sample": {"start": str(dates[0].date()), "end": str(dates[-1].date()),
                          "days": int(len(dates)), "symbols": int(M["close"].shape[1]),
                          "symbols_excluded_st_or_delisted": int(st_flag.sum()),
                          "cost_buy": COST_BUY, "cost_sell": COST_SELL,
                          "min_amount20": MIN_AMOUNT20, "min_obs": MIN_OBS, "slots": SLOT,
                          "split": str(SPLIT.date()), "split_is_days": n_is}}
    results["signals"] = {k: int(v.sum()) for k, v in
                          {"daily_ma5": sig_daily_ma5, "daily_ma10": sig_daily_ma10,
                           "mtf_ma5": sig_mtf_ma5, "mtf_ma10": sig_mtf_ma10}.items()}

    hs = bench_hs300(M)
    ew, ew_first = bench_ew_universe(M, I)
    ew_dates = dates[ew_first:]
    results["benchmark_hs300"] = {"all": metrics(hs, dates),
                                  "is": metrics(hs[:n_is], dates[:n_is]),
                                  "oos": metrics(hs[n_is:], dates[n_is:])}
    results["benchmark_equal_weight"] = {"all": metrics(ew, ew_dates),
                                         "start": str(ew_dates[0].date()),
                                         "note": "样本前段无满足流动性+历史长度门槛的股票，基准自 %s 起算" % ew_dates[0].date()}
    results["market_median_forward"] = market_forward_stats(I, M)

    def attach_j(tr):
        for t in tr:
            t["j"] = sym_idx[t["sym"]]
        return tr

    # ---------- U03 ----------
    u03 = {}
    for label, sig in (("daily_ma5", sig_daily_ma5), ("daily_ma10", sig_daily_ma10),
                       ("mtf_ma5", sig_mtf_ma5), ("mtf_ma10", sig_mtf_ma10)):
        tr = attach_j(gen_ma_exit_trades(I, M, sig))
        eq, expo, exe_m = portfolio_from_trades(tr, M, rank=True)
        eq_n, expo_n, exe_n = portfolio_from_trades(tr, M, rank=False)
        u03[label] = {
            "portfolio": {"all": metrics(eq, dates),
                          "is": metrics(eq[:n_is], dates[:n_is]),
                          "oos": metrics(eq[n_is:], dates[n_is:])},
            "portfolio_no_rank": {"all": metrics(eq_n, dates),
                                  "is": metrics(eq_n[:n_is], dates[:n_is]),
                                  "oos": metrics(eq_n[n_is:], dates[n_is:])},
            "executed_trades": trade_stats(exe_m),
            "trades": trade_stats(tr), "split": bucket_split(tr, dates),
            "exposure": float(np.mean(expo)),
            "reasons": pd.Series([t["reason"] for t in tr]).value_counts().to_dict(),
            "forward": signal_forward_stats(I, M, sig)}
    # 稳健性：加 8% 硬止损 / 提高成本
    tr_hs = attach_j(gen_ma_exit_trades(I, M, sig_mtf_ma5, hard_stop=0.08))
    eq_hs, _, _ = portfolio_from_trades(tr_hs, M)
    u03["mtf_ma5_hardstop8"] = {"portfolio": {"all": metrics(eq_hs, dates)},
                                "trades": trade_stats(tr_hs)}
    tr_cs = attach_j(gen_ma_exit_trades(I, M, sig_mtf_ma5, cb=COST_STRESS[0], cs=COST_STRESS[1]))
    eq_cs, _, _ = portfolio_from_trades(tr_cs, M)
    u03["mtf_ma5_cost_stress"] = {"portfolio": {"all": metrics(eq_cs, dates)},
                                   "trades": trade_stats(tr_cs)}
    results["u03"] = u03

    # ---------- U06 ----------
    u06 = {}
    for label, kw in (("atr2_r15", dict(r_mult=1.5)),
                      ("atr2_r20", dict(r_mult=2.0)),
                      ("atr2_r30", dict(r_mult=3.0)),
                      ("fixed8_r20", dict(r_mult=2.0, fixed_stop=0.08))):
        tr = attach_j(gen_stop_target_trades(I, M, sig_daily_ma5, **kw))
        eq, expo, exe = portfolio_from_trades(tr, M, risk=0.01, frac=0.25, slot=5)
        u06[label] = {
            "portfolio": {"all": metrics(eq, dates),
                          "is": metrics(eq[:n_is], dates[:n_is]),
                          "oos": metrics(eq[n_is:], dates[n_is:])},
            "executed_trades": trade_stats(exe),
            "trades": trade_stats(tr), "split": bucket_split(tr, dates),
            "reasons": pd.Series([t["reason"] for t in tr]).value_counts().to_dict(),
            "exposure": float(np.mean(expo))}
    # 对照组：同样的止损止盈规则，随机入场
    for label, kw in (("random_atr2_r20", dict(r_mult=2.0)),
                      ("random_fixed8_r20", dict(r_mult=2.0, fixed_stop=0.08))):
        tr = random_entry_trades(I, M, n_draws=60000, seed=2024, **kw)
        u06[label] = {"trades": trade_stats(tr), "split": bucket_split(tr, dates),
                      "reasons": pd.Series([t["reason"] for t in tr]).value_counts().to_dict()}
    # 对照：策略入场 + MA20 离场（无止损止盈），来自 U03
    u06["signal_ma20_exit"] = {"trades": u03["daily_ma5"]["trades"],
                               "split": u03["daily_ma5"]["split"]}
    results["u06"] = u06

    with open(os.path.join(OUT, "u03_u06_results.json"), "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str)[:6000])


if __name__ == "__main__":
    main()
