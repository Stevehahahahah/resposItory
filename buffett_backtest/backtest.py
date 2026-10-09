"""Portfolio simulation.

Positions are held as units of each stock's total-return index (Yahoo
adjclose), so dividends are reinvested in the stock that paid them.  Idle cash
sits in BIL (1-3 month T-bills).  Decisions use data up to the close of the
review day and trade at the next trading day's close; every trade pays COST.
"""

import numpy as np
import pandas as pd

import strategy as st

COST = 0.001


class Book:
    """Holdings plus a daily value record.

    adj: adjclose for every ticker, indexed by the trading calendar and
    forward-filled (a delisted stock keeps its last price until it is sold).
    """

    def __init__(self, adj, cash, start, value=1.0):
        self.adj, self.cash = adj, cash
        self.units, self.trades = {}, []
        self.cash_units = value / cash.at[start]
        self.curve = []
        self._marked = start

    def px(self, t, d):
        p = self.adj.at[d, t] if t in self.adj.columns else np.nan
        return None if pd.isna(p) else float(p)

    def value(self, d):
        v = self.cash_units * self.cash.at[d]
        for t, u in self.units.items():
            v += u * (self.px(t, d) or 0.0)
        return v

    def mark(self, until, inclusive=False):
        """Record daily values from the last mark up to `until` with current holdings."""
        idx = self.adj.index
        sel = idx[(idx >= self._marked) & ((idx <= until) if inclusive else (idx < until))]
        if len(sel):
            v = self.cash.loc[sel] * self.cash_units
            if self.units:
                tick = list(self.units)
                v = v + self.adj.loc[sel, tick].fillna(0.0).to_numpy() @ np.array([self.units[t] for t in tick])
            self.curve.append(pd.Series(v, index=sel))
        self._marked = until

    def _cash_in(self, amt, d):
        self.cash_units += amt / self.cash.at[d]

    def sell(self, t, d, why, amount=None):
        p = self.px(t, d) or 0.0
        full = self.units[t] * p
        amt = full if amount is None or amount >= full else amount
        if amount is None or amount >= full:
            del self.units[t]
        else:
            self.units[t] -= amt / p
        self._cash_in(amt * (1 - COST), d)
        self.trades.append({"date": d, "ticker": t, "side": "sell", "amount": amt, "reason": why})

    def buy(self, t, d, amount, why=""):
        p = self.px(t, d)
        amount = min(amount, self.cash_units * self.cash.at[d])
        if not p or amount <= 1e-9:
            return
        self.units[t] = self.units.get(t, 0.0) + amount * (1 - COST) / p
        self._cash_in(-amount, d)
        self.trades.append({"date": d, "ticker": t, "side": "buy", "amount": amount, "reason": why})

    def rebalance(self, weights, d, why=""):
        """Trade the differences to reach target weights; the rest stays in cash."""
        total = self.value(d)
        for t in list(self.units):
            have = self.units[t] * (self.px(t, d) or 0.0)
            tgt = weights.get(t, 0.0) * total
            if tgt <= 0:
                self.sell(t, d, why)
            elif have > tgt * 1.02:
                self.sell(t, d, why, amount=have - tgt)
        for t, w in sorted(weights.items(), key=lambda kv: -kv[1]):
            have = self.units.get(t, 0.0) * (self.px(t, d) or 0.0)
            if w * total > have * 1.02:
                self.buy(t, d, w * total - have, why)

    def result(self, name, log=None):
        curve = pd.concat(self.curve)
        curve = curve[~curve.index.duplicated(keep="last")]
        return {"name": name, "curve": curve, "trades": pd.DataFrame(self.trades),
                "log": pd.DataFrame(log or []), "holdings": dict(self.units)}


def next_day(cal, d):
    later = cal[cal > pd.Timestamp(d)]
    return later[0] if len(later) else None


def run_rules(name, reviews, adj, cash, metric_at, universe_at, thresholds_at, n_hold, last_price):
    """Buffett-rule portfolio, reviewed on each date in `reviews`.

    metric_at(ticker, date) -> metrics dict or None
    universe_at(date)       -> tickers to screen
    thresholds_at(date)     -> (thresholds, number of Berkshire buys they came from)
    last_price[ticker]      -> date of the last real (not forward-filled) price
    """
    cal = adj.index
    first = next_day(cal, reviews[0])
    book = Book(adj, cash, first)
    strikes, log = {}, []
    for t in reviews:
        e = next_day(cal, t)
        if e is None:
            break
        book.mark(e)
        th, n_used = thresholds_at(t)
        th = {**th, "n_hold": n_hold}
        for h in list(book.units):
            if last_price.get(h, t) < t - pd.Timedelta(days=10):
                book.sell(h, e, "delisted / no price")
                continue
            m = metric_at(h, t)
            bad = st.failures(m, th)
            strikes[h] = strikes.get(h, 0) + 1 if bad else 0
            if strikes[h] >= 2:
                book.sell(h, e, "quality broke twice: " + ",".join(bad))
            elif m is not None and m["mos"] < -th["sell_over"]:
                book.sell(h, e, f"price {1 - m['mos']:.2f}x intrinsic value")
        cands = []
        for tk in universe_at(t):
            if tk in book.units:
                continue
            m = metric_at(tk, t)
            if st.buyable(m, th) and book.px(tk, e):
                cands.append((m["mos"], tk))
        cands.sort(reverse=True)
        size = book.value(e) / n_hold
        for mos, tk in cands[:max(n_hold - len(book.units), 0)]:
            book.buy(tk, e, size, f"margin of safety {mos:.0%}")
            strikes[tk] = 0
        v = book.value(e)
        log.append({"date": t, "holdings": len(book.units), "candidates": len(cands),
                    "cash_pct": book.cash_units * cash.at[e] / v, "buys_used": n_used,
                    **{f"th_{k}": th[k] for k in st.CALIBRATED}})
    book.mark(cal[-1], inclusive=True)
    return book.result(name, log)


def run_weights(name, events, adj, cash, start):
    """Follow dated target weights, e.g. Berkshire's 13F as each one is filed."""
    cal = adj.index
    first = next_day(cal, start)
    book = Book(adj, cash, first)
    for d, w in events:
        e = next_day(cal, max(d, start))
        if e is None:
            break
        book.mark(e)
        book.rebalance(w, e, "13F")
    book.mark(cal[-1], inclusive=True)
    return book.result(name)


def stats(curve, cash):
    """Total and annual return, volatility, max drawdown, Sharpe (over T-bills)."""
    curve = curve.dropna()
    r = curve.pct_change().dropna()
    rf = cash.reindex(curve.index).pct_change().reindex(r.index).fillna(0)
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    ex = r - rf
    return {
        "total_return": curve.iloc[-1] / curve.iloc[0] - 1,
        "cagr": (curve.iloc[-1] / curve.iloc[0]) ** (1 / years) - 1,
        "volatility": r.std() * np.sqrt(252),
        "max_drawdown": (curve / curve.cummax() - 1).min(),
        "sharpe": ex.mean() / ex.std() * np.sqrt(252) if ex.std() > 0 else float("nan"),
        "start": curve.index[0].date(), "end": curve.index[-1].date(),
    }


def yearly(curve):
    """Calendar-year returns (the first year counts from the start date)."""
    ends = curve.groupby(curve.index.year).last()
    starts = pd.concat([pd.Series([curve.iloc[0]], index=[curve.index[0].year]), ends.iloc[:-1]])
    starts.index = ends.index
    return ends / starts.values - 1
