"""Cached downloads: SEC EDGAR, Yahoo Finance prices, Wikipedia S&P 500 membership.

Every response is written under cache/ and reused on the next run, so a full
backtest only hits the network once.  SEC asks for a User-Agent that names the
requester (set SEC_USER_AGENT) and at most 10 requests per second.
"""

import io
import json
import os
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"

SEC_UA = os.environ.get("SEC_USER_AGENT", "buffett-backtest (github.com/stevehahahahah)")
WEB_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

_session = requests.Session()
_last_sec = [0.0]


def _fetch(url, ua, sec=False, tries=4):
    """GET with retries; returns the Response, or None on 404."""
    for i in range(tries):
        if sec:
            wait = 0.12 - (time.time() - _last_sec[0])
            if wait > 0:
                time.sleep(wait)
            _last_sec[0] = time.time()
        try:
            r = _session.get(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"},
                             timeout=60)
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))
            continue
        if r.status_code == 404:
            return None
        if r.status_code in (429, 500, 502, 503, 504) and i < tries - 1:
            time.sleep(2 ** (i + 1))
            continue
        r.raise_for_status()
        return r
    return None


def cached(url, path, ua=WEB_UA, sec=False, binary=False):
    """Return the body of url, cached at CACHE/path.  None if the server says 404."""
    p = CACHE / path
    miss = p.with_suffix(p.suffix + ".404")
    if p.exists():
        return p.read_bytes() if binary else p.read_text(encoding="utf-8")
    if miss.exists():
        return None
    r = _fetch(url, ua, sec=sec)
    p.parent.mkdir(parents=True, exist_ok=True)
    if r is None:
        miss.touch()
        return None
    if binary:
        p.write_bytes(r.content)
        return r.content
    p.write_text(r.text, encoding="utf-8")
    return r.text


# ---------------------------------------------------------------- SEC EDGAR

def sec_json(url, path):
    body = cached(url, path, ua=SEC_UA, sec=True)
    return None if body is None else json.loads(body)


def sec_tickers():
    """Current ticker -> CIK map from SEC (tickers use '-' like Yahoo: BRK-B)."""
    d = sec_json("https://www.sec.gov/files/company_tickers.json", "sec/company_tickers.json")
    df = pd.DataFrame(d.values()).rename(columns={"cik_str": "cik"})
    df["ticker"] = df["ticker"].str.upper().str.replace(".", "-", regex=False)
    return df[["ticker", "cik", "title"]].drop_duplicates("ticker")


def companyfacts(cik):
    cik = int(cik)
    return sec_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
                    f"sec/companyfacts/CIK{cik:010d}.json")


def submissions(cik):
    """Company metadata (SIC code, names) plus the full filing list."""
    cik = int(cik)
    d = sec_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
                 f"sec/submissions/CIK{cik:010d}.json")
    if d is None:
        return None
    frames = [pd.DataFrame(d["filings"]["recent"])]
    for f in d["filings"].get("files", []):
        more = sec_json(f"https://data.sec.gov/submissions/{f['name']}", f"sec/submissions/{f['name']}")
        if more:
            frames.append(pd.DataFrame(more))
    d["filing_table"] = pd.concat(frames, ignore_index=True)
    return d


def sec_archive(cik, accession, name, binary=False):
    """A file inside one EDGAR filing folder."""
    acc = accession.replace("-", "")
    return cached(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{name}",
                  f"sec/archives/{int(cik)}/{acc}/{name}", ua=SEC_UA, sec=True, binary=binary)


def sec_full_submission(cik, accession):
    """The complete .txt submission (header + every document) of one filing."""
    acc = accession.replace("-", "")
    return cached(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{accession}.txt",
                  f"sec/archives/{int(cik)}/{acc}/{accession}.txt", ua=SEC_UA, sec=True)


# ---------------------------------------------------------------- prices

def _epoch(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def yahoo_chart(symbol, start=date(2005, 1, 1), end=None):
    """Daily prices for a Yahoo symbol.

    Returns (prices, splits):
      prices  DataFrame indexed by date with columns close (split-adjusted to
              today's share count) and adjclose (split- and dividend-adjusted,
              i.e. a total-return index);
      splits  Series of split ratios (new shares per old share) by ex-date.
    None if Yahoo has no data for the symbol.
    """
    end = end or date.today()
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?period1={_epoch(start)}&period2={_epoch(end)}&interval=1d"
           f"&events=div%2Csplit&includeAdjustedClose=true")
    body = cached(url, f"yahoo/{symbol}_{start}_{end}.json")
    if body is None:
        return None
    d = json.loads(body)
    res = (d.get("chart") or {}).get("result")
    if not res or not res[0].get("timestamp"):
        return None
    return parse_yahoo_chart(res[0])


def parse_yahoo_chart(res):
    off = res.get("meta", {}).get("gmtoffset", 0)
    idx = pd.to_datetime([t + off for t in res["timestamp"]], unit="s").normalize()
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose", q["close"])
    prices = pd.DataFrame({"close": q["close"], "adjclose": adj}, index=idx, dtype=float)
    prices = prices[~prices.index.duplicated(keep="last")].dropna(how="all").ffill()
    sp = (res.get("events") or {}).get("splits") or {}
    splits = pd.Series({pd.Timestamp(v["date"] + off, unit="s").normalize():
                        v["numerator"] / v["denominator"] for v in sp.values()}, dtype=float)
    return prices, splits.sort_index()


def stooq_daily(symbol):
    """Fallback price source (US tickers as 'aapl.us').  Close is split-adjusted."""
    body = cached(f"https://stooq.com/q/d/l/?s={symbol.lower()}&i=d", f"stooq/{symbol.lower()}.csv")
    if not body or not body.startswith("Date"):
        return None
    df = pd.read_csv(io.StringIO(body), parse_dates=["Date"], index_col="Date")
    return df.rename(columns=str.lower)[["close"]]


def split_factor_between(splits, after, upto):
    """Product of split ratios with after < ex-date <= upto.

    Shares reported for a period ending `after` must be multiplied by this to
    be comparable with a raw price on `upto`.
    """
    if splits is None or splits.empty:
        return 1.0
    s = splits[(splits.index > pd.Timestamp(after)) & (splits.index <= pd.Timestamp(upto))]
    return float(s.prod()) if len(s) else 1.0


# ---------------------------------------------------------------- S&P 500 membership

def _norm_ticker(t):
    return str(t).strip().upper().replace(".", "-")


def sp500_tables():
    """(current constituents, change log) from Wikipedia."""
    html = cached("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "wiki/sp500.html")
    tables = pd.read_html(io.StringIO(html))
    cur = tables[0].copy()
    cur["Symbol"] = cur["Symbol"].map(_norm_ticker)
    ch = tables[1].copy()
    ch.columns = ["_".join(str(x) for x in c).strip() if isinstance(c, tuple) else str(c)
                  for c in ch.columns]
    col = {c: c for c in ch.columns}
    for c in ch.columns:
        lc = c.lower()
        if lc.startswith("date") or lc.startswith("effective date"):
            col[c] = "date"
        elif "added" in lc and "ticker" in lc:
            col[c] = "added"
        elif "added" in lc and "security" in lc:
            col[c] = "added_name"
        elif "removed" in lc and "ticker" in lc:
            col[c] = "removed"
        elif "removed" in lc and "security" in lc:
            col[c] = "removed_name"
    ch = ch.rename(columns=col)
    ch["date"] = pd.to_datetime(ch["date"], errors="coerce")
    ch = ch.dropna(subset=["date"])
    for c in ("added", "removed"):
        ch[c] = ch[c].map(lambda t: _norm_ticker(t) if isinstance(t, str) and t.strip() else None)
    return cur, ch.sort_values("date")


def sp500_members(on, current, changes):
    """Tickers in the index on a date, by undoing every later change."""
    members = set(current["Symbol"])
    later = changes[changes["date"] > pd.Timestamp(on)].sort_values("date", ascending=False)
    for added, removed in zip(later["added"], later["removed"]):
        if isinstance(added, str) and added:
            members.discard(added)
        if isinstance(removed, str) and removed:
            members.add(removed)
    return members


def _name_tokens(s):
    s = re.sub(r"[^a-z0-9 ]", " ", str(s).lower().replace("'", ""))
    stop = {"inc", "corp", "corporation", "co", "company", "the", "ltd", "plc", "group",
            "holdings", "holding", "class", "a", "b", "c", "com", "new", "de", "and"}
    return {w for w in s.split() if w not in stop}


def names_match(a, b):
    ta, tb = _name_tokens(a), _name_tokens(b)
    return bool(ta and tb) and len(ta & tb) / min(len(ta), len(tb)) >= 0.5


def resolve_ciks(tickers, current, changes, sec_map):
    """ticker -> CIK for every ticker that was ever a member.

    Current members carry a CIK on Wikipedia.  For removed members the SEC map
    only knows today's owner of the ticker, which may be a different company,
    so the names must agree.
    """
    out = {}
    cur_cik = dict(zip(current["Symbol"], current.get("CIK", pd.Series(dtype=float))))
    names = {}
    for t, n in zip(changes["removed"], changes.get("removed_name", changes["removed"])):
        if isinstance(t, str):
            names[t] = n
    sec = sec_map.set_index("ticker")
    for t in tickers:
        if t in cur_cik and pd.notna(cur_cik[t]):
            out[t] = int(cur_cik[t])
        elif t in sec.index and (t not in names or names_match(names[t], sec.at[t, "title"])):
            out[t] = int(sec.at[t, "cik"])
    return out
