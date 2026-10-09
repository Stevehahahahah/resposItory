"""Buffett's rules as code: quality tests, owner-earnings DCF, thresholds.

Prices here are always in today's share basis (Yahoo's split-adjusted close),
so every share count is converted to that basis too: a count is multiplied by
the splits that happened after it was filed.
"""

import math

import numpy as np
import pandas as pd

from data import split_factor_between

FAR = pd.Timestamp("2100-01-01")

# Fixed thresholds (strategy A).  See principles.md for where each comes from.
DEFAULTS = {
    "roe_avg": 0.15,       # average return on equity, last 5 fiscal years
    "roe_floor": 0.12,     # no single year below this
    "gm_drop": 0.05,       # gross margin may fall at most 5 points over 5 years
    "debt_years": 3.0,     # long-term debt payable from <= 3 years of earnings
    "dilution": 0.02,      # share count up at most 2% over 5 years
    "mos": 0.25,           # buy only at >= 25% below intrinsic value
    "sell_over": 0.5,      # sell when price > 1.5 x intrinsic value
    "discount": 0.10,
    "terminal": 0.03,
    "growth_cap": 0.10,
    "n_hold": 10,
}
CALIBRATED = ("roe_avg", "roe_floor", "debt_years", "mos")


def dcf(oe, g, r=0.10, gt=0.03, years=10):
    """Owner earnings growing at g for `years`, then gt forever, discounted at r."""
    pv = sum(oe * (1 + g) ** i / (1 + r) ** i for i in range(1, years + 1))
    tv = oe * (1 + g) ** years * (1 + gt) / (r - gt) / (1 + r) ** years
    return pv + tv


def cagr(a, b, n):
    if a > 0 and b > 0 and n > 0:
        return (b / a) ** (1 / n) - 1
    return float("nan")


def price_on(px, d, tol=10):
    """Last close on or before d, if it is no older than tol days."""
    s = px.loc[:pd.Timestamp(d)].dropna()
    if s.empty or (pd.Timestamp(d) - s.index[-1]).days > tol:
        return None
    return float(s.iloc[-1])


def _roe(ni, eq, debt):
    """Return on equity; on capital (equity + debt) when equity is negative from buybacks."""
    out = []
    for i in range(1, len(ni)):
        e0, e1 = eq.iloc[i - 1], eq.iloc[i]
        if e1 > 0:
            base = (e0 + e1) / 2 if e0 > 0 else e1
        else:
            cap = (e1 if pd.notna(e1) else 0) + (debt.iloc[i] if pd.notna(debt.iloc[i]) else 0)
            base = cap if cap > 0 and pd.notna(e1) else float("nan")
        out.append(ni.iloc[i] / base if base and pd.notna(base) else float("nan"))
    return pd.Series(out, index=ni.index[1:])


def metrics(snap, px, splits, shares, shares_filed, asof, p=DEFAULTS):
    """Every number the rules look at, from a fundamentals snapshot and prices.

    snap: Company.snapshot(asof) (6 fiscal years); px: split-adjusted closes;
    shares, shares_filed: Company.latest_shares(asof).
    """
    if snap is None or len(snap) < 5 or not shares:
        return None
    s = snap.sort_index()
    ni, eq = s["net_income"], s["equity"]
    debt = s["lt_debt"].fillna(0.0)
    roe = _roe(ni, eq, debt).iloc[-5:]
    last5 = s.iloc[-5:]
    n5 = last5["net_income"]
    gm = (last5["gross_profit"] / last5["revenue"]).replace([np.inf, -np.inf], np.nan).dropna()

    oe = last5["net_income"] + last5["da"] - last5["capex"]
    alt = last5["ocf"] - last5["capex"]
    oe = oe.fillna(alt).dropna()
    oe_base = oe.iloc[-3:].mean() if len(oe) >= 2 else float("nan")

    today = [x * split_factor_between(splits, f, FAR) if pd.notna(x) and pd.notna(f) else float("nan")
             for x, f in zip(s["diluted_shares"], s["shares_filed"])]
    sh = pd.Series(today, index=s.index)
    sh5 = sh.iloc[-5:].dropna()
    dilution = sh5.iloc[-1] / sh5.iloc[0] - 1 if len(sh5) >= 2 else float("nan")

    g = cagr(n5.iloc[0], n5.iloc[-1], len(n5) - 1)
    g = 0.0 if math.isnan(g) else min(max(g, 0.0), p["growth_cap"])
    iv = dcf(oe_base, g, p["discount"], p["terminal"]) if oe_base > 0 else float("nan")

    price = price_on(px, asof)
    shares_now = shares * split_factor_between(splits, shares_filed, FAR)
    mcap = price * shares_now if price else float("nan")
    mos = 1 - mcap / iv if iv and iv > 0 and mcap == mcap else float("-inf")

    # Buffett's $1 test: market value added per dollar of earnings kept in the business.
    start = s.index[-6] if len(s) >= 6 else s.index[-5]
    kept = s.loc[s.index > start]
    retained = (kept["net_income"] - kept["dividends"].fillna(0) - kept["buybacks"].fillna(0)).sum()
    p0, p1 = price_on(px, start), price_on(px, s.index[-1])
    mv0 = p0 * sh.loc[start] if p0 and pd.notna(sh.loc[start]) else float("nan")
    mv1 = p1 * sh.iloc[-1] if p1 and pd.notna(sh.iloc[-1]) else float("nan")
    dollar = (mv1 - mv0) / retained if retained > 0 else float("inf")

    avg_ni = n5.iloc[-3:].mean()
    return {
        "asof": pd.Timestamp(asof), "fy_end": s.index[-1], "years": len(s),
        "roe_avg": roe.mean(), "roe_min": roe.min(), "roe_years": int(roe.notna().sum()),
        "gm_last": gm.iloc[-1] if len(gm) else float("nan"),
        "gm_drop": gm.iloc[0] - gm.iloc[-1] if len(gm) >= 2 else float("nan"),
        "debt_years": debt.iloc[-1] / avg_ni if avg_ni > 0 else float("inf"),
        "ni_positive": bool((n5 > 0).all()), "ni_growth": n5.iloc[-1] / n5.iloc[0] - 1 if n5.iloc[0] > 0 else float("nan"),
        "growth": g, "owner_earnings": oe_base, "dilution": dilution, "dollar_test": dollar,
        "price": price, "market_cap": mcap, "intrinsic_value": iv, "mos": mos,
        "iv_per_share": iv / shares_now if shares_now else float("nan"),
        "pe": mcap / n5.iloc[-1] if n5.iloc[-1] > 0 else float("nan"),
        "p_oe": mcap / oe_base if oe_base > 0 else float("nan"),
    }


def failures(m, th):
    """Quality rules a company breaks (valuation excluded).  Empty list = a wonderful business."""
    if m is None:
        return ["no data"]
    bad = []
    if m["roe_years"] < 4 or not m["roe_avg"] >= th["roe_avg"]:
        bad.append("roe_avg")
    if not m["roe_min"] >= th["roe_floor"]:
        bad.append("roe_floor")
    if m["gm_drop"] == m["gm_drop"] and m["gm_drop"] > th["gm_drop"]:
        bad.append("gross_margin")
    if not m["debt_years"] <= th["debt_years"]:
        bad.append("debt")
    if not m["ni_positive"]:
        bad.append("losses")
    if not m["ni_growth"] > 0:
        bad.append("no_growth")
    if not m["owner_earnings"] > 0:
        bad.append("owner_earnings")
    if m["dilution"] == m["dilution"] and m["dilution"] > th["dilution"]:
        bad.append("dilution")
    if m["dollar_test"] == m["dollar_test"] and m["dollar_test"] < 1:
        bad.append("dollar_test")
    return bad


def buyable(m, th):
    return m is not None and m["price"] is not None and not failures(m, th) and m["mos"] >= th["mos"]


def calibrate(buys, asof, base=DEFAULTS, q=0.25, min_n=8):
    """Thresholds learned from Berkshire's own purchases disclosed by asof.

    Each threshold is set so that 1 - q of his actual buys would have passed
    it.  Until min_n buys with data are known, the fixed defaults apply.
    """
    th = dict(base)
    if buys is None or buys.empty:
        return th, 0
    b = buys[(buys["known"] <= pd.Timestamp(asof))]
    b = b.replace([np.inf, -np.inf], np.nan)
    if len(b) < min_n:
        return th, len(b)
    th["roe_avg"] = float(b["roe_avg"].quantile(q))
    th["roe_floor"] = float(b["roe_min"].quantile(q))
    th["debt_years"] = float(b["debt_years"].fillna(b["debt_years"].max()).quantile(1 - q))
    th["mos"] = float(b["mos"].quantile(q))
    return th, len(b)
