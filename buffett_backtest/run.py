#!/usr/bin/env python3
"""Backtest Buffett's rules on S&P 500 stocks, 2015 to today, and pick today's portfolio.

  A  fixed thresholds (DEFAULTS in strategy.py)
  B  thresholds learned from Berkshire's own 13F purchases known at each date
  C  copy Berkshire's 13F as each one is filed
  benchmarks: SPY and BRK-B, total return

Usage:  python run.py [--start 2015-01-01] [--end YYYY-MM-DD]
Needs network access to SEC, Yahoo Finance, Wikipedia and OpenFIGI (see README).
"""

import argparse
import pickle
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
import berkshire_13f as b13
import data
import strategy as st
from fundamentals import Company

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
PRICE_START = date(2004, 1, 1)


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def quarter_starts(cal, start, end):
    """First trading day of each Jan / Apr / Jul / Oct."""
    out = []
    for q in pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="QS-JAN"):
        d = cal[cal >= q]
        if len(d) and d[0] <= pd.Timestamp(end):
            out.append(d[0])
    return out


class Universe:
    """Prices, fundamentals and metadata for every ticker the backtest touches."""

    def __init__(self, end):
        self.end = end
        self.prices, self.splits, self.companies, self.sic, self.cik = {}, {}, {}, {}, {}

    def load_price(self, t):
        if t in self.prices:
            return self.prices[t] is not None
        r = data.yahoo_chart(t, PRICE_START, self.end)
        if r is None:
            self.prices[t] = None
            return False
        self.prices[t], self.splits[t] = r
        return True

    def load_company(self, t, cik):
        self.cik[t] = cik
        if cik not in self.companies:
            cf = data.companyfacts(cik)
            self.companies[cik] = Company(cf) if cf else None
            sub = data.submissions(cik)
            self.sic[cik] = int(sub["sic"]) if sub and str(sub.get("sic") or "").isdigit() else None
        return self.companies[cik] is not None

    def financial(self, t):
        s = self.sic.get(self.cik.get(t))
        return s is not None and 6000 <= s <= 6799

    def metrics(self, t, asof, p=st.DEFAULTS):
        comp = self.companies.get(self.cik.get(t))
        if comp is None or self.prices.get(t) is None:
            return None
        snap = comp.snapshot(asof)
        shares, filed = comp.latest_shares(asof)
        return st.metrics(snap, self.prices[t]["close"], self.splits[t], shares, filed, asof, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default=str(date.today()))
    a = ap.parse_args()
    end = date.fromisoformat(a.end)
    RESULTS.mkdir(exist_ok=True)
    U = Universe(end)

    # ---- calendar, cash, benchmarks
    for t in ("SPY", "BRK-B", "BIL"):
        assert U.load_price(t), f"no prices for {t}"
    cal = U.prices["SPY"].loc[a.start:].index
    reviews = quarter_starts(cal, a.start, cal[-1])

    # ---- S&P 500 members over time
    log("S&P 500 membership ...")
    cur, changes = data.sp500_tables()
    members = {d: data.sp500_members(d, cur, changes) for d in reviews}
    ever = sorted(set().union(*members.values()))
    sec_map = data.sec_tickers()
    ciks = data.resolve_ciks(ever, cur, changes, sec_map)

    # ---- Berkshire's 13F and its purchases
    log("Berkshire 13F filings ...")
    h, checks = b13.all_filings()
    h.to_csv(data.CACHE / "berkshire_13f.csv", index=False)
    checks.to_csv(RESULTS / "berkshire_13f_checks.csv", index=False)
    b13.build_cusip_map(h, sec_map)
    cmap = b13.cusip_to_ticker()
    buys = b13.new_buys(h, cmap)
    sec_cik = dict(zip(sec_map["ticker"], sec_map["cik"]))

    # ---- load data for every ticker
    tickers = sorted(set(ever) | set(buys["ticker"]) | set(h["cusip"].map(cmap).dropna()))
    log(f"loading {len(tickers)} tickers ...")
    for i, t in enumerate(tickers):
        if i % 50 == 0:
            log(f"  {i}/{len(tickers)}")
        try:
            U.load_price(t)
        except Exception as e:                           # noqa: BLE001  (one bad symbol must not stop the run)
            log(f"  price {t}: {e}")
            U.prices[t] = None
        cik = ciks.get(t) or sec_cik.get(t)
        if cik:
            try:
                U.load_company(t, cik)
            except Exception as e:                       # noqa: BLE001
                log(f"  facts {t}: {e}")

    adj = pd.DataFrame({t: p["adjclose"] for t, p in U.prices.items() if p is not None})
    adj = adj.reindex(adj.index.union(cal)).ffill().reindex(cal)
    last_price = {t: p["adjclose"].dropna().index.max() for t, p in U.prices.items() if p is not None}
    cash = adj["BIL"]

    # ---- metrics of every stock at every review (cached: the slow part)
    mpath = data.CACHE / f"metrics_{a.start}_{end}.pkl"
    M = pickle.loads(mpath.read_bytes()) if mpath.exists() else {}
    log("metrics ...")
    for d in reviews:
        for t in members[d]:
            if (t, d) not in M:
                M[(t, d)] = U.metrics(t, d) if t in U.cik and not U.financial(t) else None
    mpath.write_bytes(pickle.dumps(M))

    def metric_at(t, d):
        if (t, d) not in M:
            M[(t, d)] = U.metrics(t, d) if t in U.cik else None
        return M[(t, d)]

    # one entry per company (GOOGL/GOOG, FOX/FOXA ...): first ticker wins
    def universe_at(d):
        seen, out = set(), []
        for t in sorted(members[d]):
            c = U.cik.get(t)
            if c and c not in seen and not U.financial(t):
                seen.add(c)
                out.append(t)
        return out

    # ---- what Berkshire's buys looked like when it bought them
    log("metrics of Berkshire's purchases ...")
    rows = []
    for b in buys.itertuples():
        cik = sec_cik.get(b.ticker)
        if not cik or not U.load_price(b.ticker) or not U.load_company(b.ticker, cik) or U.financial(b.ticker):
            continue
        m = U.metrics(b.ticker, b.period)
        if m:
            rows.append({"ticker": b.ticker, "name": b.name, "period": b.period, "known": b.known,
                         "value": b.value, **{k: m[k] for k in ("roe_avg", "roe_min", "debt_years", "mos",
                                                               "pe", "p_oe", "growth", "dilution", "gm_last")}})
    bm = pd.DataFrame(rows)
    bm.to_csv(RESULTS / "berkshire_buys_metrics.csv", index=False)

    learned = lambda d: st.calibrate(bm, d)                        # noqa: E731

    # ---- strategies
    runs = []
    log("backtests ...")
    for n in (8, 10, 15):
        for mos in (0.15, 0.25, 0.35):
            p = {**st.DEFAULTS, "mos": mos}
            runs.append(bt.run_rules(f"A mos={mos:.0%} n={n}", reviews, adj, cash, metric_at, universe_at,
                                     lambda d, p=p: (p, 0), n, last_price))
        runs.append(bt.run_rules(f"B n={n}", reviews, adj, cash, metric_at, universe_at, learned, n, last_price))

    events = []
    filings = [pd.Timestamp(f) for f in sorted(h["filed"].unique())]
    before = [f for f in filings if f <= reviews[0]]
    for f in before[-1:] + [f for f in filings if f > reviews[0]]:   # only the last one before the start matters
        periods = h[h["filed"] <= f]["period"]
        pos = b13.known_positions(h, periods.max(), f).assign(ticker=lambda x: x["cusip"].map(cmap))
        pos = pos[pos["ticker"].isin(adj.columns)]
        w = pos.groupby("ticker")["value"].sum()
        total = b13.known_positions(h, periods.max(), f)["value"].sum()
        events.append((f, (w / total).to_dict() if total > 0 else {}))
    runs.append(bt.run_weights("C copy Berkshire 13F", events, adj, cash, reviews[0]))

    first = bt.next_day(cal, reviews[0])
    for t in ("SPY", "BRK-B"):
        runs.append({"name": f"{t} buy & hold", "curve": adj[t].loc[first:] / adj[t].at[first],
                     "trades": pd.DataFrame(), "log": pd.DataFrame(), "holdings": {t: 1}})

    # ---- report
    table = pd.DataFrame([{"strategy": r["name"], **bt.stats(r["curve"], cash),
                           "trades": len(r["trades"])} for r in runs]).set_index("strategy")
    yearly = pd.DataFrame({r["name"]: bt.yearly(r["curve"]) for r in runs})
    coverage = pd.DataFrame([{
        "date": d.date(), "members": len(members[d]),
        "with_cik": sum(t in U.cik for t in members[d]),
        "with_prices": sum(U.prices.get(t) is not None for t in members[d]),
        "screened": len(universe_at(d)),
        "with_metrics": sum(M.get((t, d)) is not None for t in members[d]),
        "quality_pass": sum(not st.failures(M.get((t, d)), st.DEFAULTS) for t in members[d]),
        "buyable_A": sum(st.buyable(M.get((t, d)), st.DEFAULTS) for t in members[d]),
    } for d in reviews])

    main_runs = {r["name"]: r for r in runs}
    a_run, b_run = main_runs["A mos=25% n=10"], main_runs["B n=10"]
    pick = max((a_run, b_run), key=lambda r: table.at[r["name"], "sharpe"])

    today = cal[-1]
    th_now = st.calibrate(bm, today)[0] if pick is b_run else dict(st.DEFAULTS)
    cur_rows = []
    for t in universe_at(reviews[-1]):
        m = U.metrics(t, today)
        if st.buyable(m, th_now):
            cur_rows.append({"ticker": t, "price": m["price"], "intrinsic_value_per_share": m["iv_per_share"],
                             "margin_of_safety": m["mos"], "roe_avg_5y": m["roe_avg"],
                             "debt_years": m["debt_years"], "pe": m["pe"], "p_owner_earnings": m["p_oe"]})
    current = pd.DataFrame(cur_rows).sort_values("margin_of_safety", ascending=False).head(10) \
        if cur_rows else pd.DataFrame()
    if not current.empty:
        current["weight"] = 1 / 10
    current.to_csv(RESULTS / "current_portfolio.csv", index=False)

    last13f = events[-1][1] if events else {}
    pd.Series(last13f, name="weight").sort_values(ascending=False).to_csv(RESULTS / "berkshire_latest_13f.csv")

    for r in runs:
        if not r["trades"].empty:
            safe = r["name"].replace(" ", "_").replace("=", "").replace("%", "").replace("&", "and")
            r["trades"].to_csv(RESULTS / f"trades_{safe}.csv", index=False)
    a_run["log"].to_csv(RESULTS / "review_log_A.csv", index=False)
    b_run["log"].to_csv(RESULTS / "review_log_B.csv", index=False)
    coverage.to_csv(RESULTS / "coverage.csv", index=False)
    table.to_csv(RESULTS / "summary.csv")
    yearly.to_csv(RESULTS / "yearly.csv")

    plot(runs, ["A mos=25% n=10", "B n=10", "C copy Berkshire 13F", "SPY buy & hold", "BRK-B buy & hold"])
    write_summary(table, yearly, coverage, bm, checks, pick["name"], th_now, current, end)
    log(table[["cagr", "total_return", "max_drawdown", "sharpe"]].to_string())


def plot(runs, names):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=120)
    for r in runs:
        if r["name"] in names:
            ax.plot(r["curve"].index, r["curve"].values, label=r["name"], lw=1.6)
    ax.set_yscale("log")
    ax.set_ylabel("Growth of $1 (log scale)")
    ax.grid(alpha=0.3)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(RESULTS / "equity_curve.png")


def pct(x):
    return "" if pd.isna(x) else f"{x:.1%}"


def write_summary(table, yearly, coverage, bm, checks, pick, th, current, end):
    t = table.copy()
    for c in ("total_return", "cagr", "volatility", "max_drawdown"):
        t[c] = t[c].map(pct)
    t["sharpe"] = t["sharpe"].map(lambda x: f"{x:.2f}")
    y = yearly.map(pct)
    chk = checks.dropna(subset=["cover_total"])
    chk = chk[chk["cover_total"] > 0]
    mism = (abs(chk["table_total"] / chk["cover_total"] - 1) > 0.01).sum()
    lines = [
        f"# 回测结果（截至 {end}）", "",
        "![equity curve](equity_curve.png)", "",
        "## 各策略表现", "", t.to_markdown(), "",
        "## 逐年收益", "", y.to_markdown(), "",
        f"## 今日持仓（按 {pick} 的规则）", "",
        "阈值：" + "，".join(f"{k}={th[k]:.3g}" for k in st.CALIBRATED), "",
        current.to_markdown(index=False, floatfmt=".3g") if not current.empty else "今天没有满足全部条件的股票：按规则应持有现金（BIL）。",
        "", "## 伯克希尔真实买入时的指标（2009 年后、非金融股）", "",
        bm[["roe_avg", "roe_min", "debt_years", "mos", "pe", "p_oe"]].describe().map(lambda v: f"{v:.3g}").to_markdown()
        if not bm.empty else "（无数据）", "",
        "## 数据检查", "",
        f"- 13F 文件 {len(checks)} 份；表内合计与封面总额相差 >1% 的：{mism} 份",
        f"- 每个复查日的数据覆盖见 coverage.csv（最低 {coverage['with_metrics'].min()} / {coverage['members'].max()} 只有完整指标）",
    ]
    (RESULTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
