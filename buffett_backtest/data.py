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
YAHOO_UA = "Mozilla/5.0"          # Yahoo answers 429 to a full browser string from cloud IPs

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
    body = cached(url, f"yahoo/{symbol}_{start}_{end}.json", ua=YAHOO_UA)
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
#
# Daily membership since 1996 comes from github.com/fja05680/sp500 (Andreas
# Clenow's list, kept up to date from S&P announcements).  It records the
# ticker each company had on that day, so FB in 2015, META today.  Company
# names and CIKs come from Wikipedia: today's constituent table, plus an
# August 2026 revision that still had the long table of index changes.

FJA_URL = ("https://raw.githubusercontent.com/fja05680/sp500/master/"
           "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv")
WIKI_URL = "https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies"
WIKI_REV = 1368675864          # 10 Aug 2026, the last revision with the change log


def _norm_ticker(t):
    return str(t).strip().upper().replace(".", "-")


def sp500_history():
    """Series: date -> set of tickers in the index that day."""
    body = cached(FJA_URL, "sp500/history.csv")
    df = pd.read_csv(io.StringIO(body), parse_dates=["date"])
    return pd.Series({r.date: {_norm_ticker(t) for t in r.tickers.split(",")} for r in df.itertuples()}).sort_index()


def sp500_members(on, hist):
    """Tickers in the index on a date (the last list on or before it)."""
    past = hist.loc[:pd.Timestamp(on)]
    return set(past.iloc[-1]) if len(past) else set()


def _wiki_tables(html):
    tables = pd.read_html(io.StringIO(html))
    cur = tables[0].copy()
    cur["Symbol"] = cur["Symbol"].map(_norm_ticker)
    ch = None
    for t in tables[1:]:
        if isinstance(t.columns, pd.MultiIndex) and "Added" in t.columns.get_level_values(0):
            ch = t.copy()
            ch.columns = ["date", "added", "added_name", "removed", "removed_name", "reason"][:len(ch.columns)]
            ch["date"] = pd.to_datetime(ch["date"], errors="coerce")
            for c in ("added", "removed"):
                ch[c] = ch[c].map(lambda t: _norm_ticker(t) if isinstance(t, str) and t.strip() else None)
            ch = ch.dropna(subset=["date"])
    return cur, ch


def sp500_wikipedia():
    """(today's constituents, constituents in Aug 2026, change log up to Aug 2026)."""
    now = cached("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "wiki/sp500.html")
    old = cached(f"{WIKI_URL}&oldid={WIKI_REV}", f"wiki/sp500_rev{WIKI_REV}.html")
    cur, _ = _wiki_tables(now)
    cur_old, changes = _wiki_tables(old)
    return cur, cur_old, changes


def membership_spans(hist):
    """ticker -> list of (first day, last day) in the index."""
    spans, open_ = {}, {}
    dates = list(hist.index)
    prev = set()
    for d, members in zip(dates, hist.values):
        for t in members - prev:
            open_[t] = d
        for t in prev - members:
            spans.setdefault(t, []).append((open_.pop(t), d))
        prev = members
    for t, d0 in open_.items():
        spans.setdefault(t, []).append((d0, None))
    return spans


def find_renames(hist, changes, added, window=5, since="2010-01-01"):
    """old ticker -> new ticker, for symbol changes.

    A rename shows up as one ticker leaving and another arriving on the same
    day, but so does an index change.  It counts as a rename only if the new
    ticker's company had already joined the index when the old ticker did
    (Wikipedia's "Date added" keeps the original date across renames: META
    shows 2013, when it was FB), the pair is not in the change log, and the
    pairing is unambiguous.
    """
    spans = membership_spans(hist)
    starts = [(d0, t) for t, ss in spans.items() for d0, _ in ss]
    listed_add = {(r.added, r.date) for r in changes.itertuples() if r.added}
    listed_rem = {(r.removed, r.date) for r in changes.itertuples() if r.removed}

    def listed(pairs, t, d):
        return any(t == x and abs((d - y).days) <= window for x, y in pairs)

    out = {}
    for old, ss in spans.items():
        for begin, end in ss:
            if end is None or end < pd.Timestamp(since) or listed(listed_rem, old, end):
                continue
            cands = [t for d0, t in starts if 0 <= (d0 - end).days <= window and t != old
                     and not listed(listed_add, t, d0)
                     and t in added and added[t] <= begin + pd.Timedelta(days=window)]
            if len(cands) == 1:
                out[old] = (cands[0], begin)
    # Two old tickers pointing at one new ticker (two companies left that day):
    # the one whose own join date matches the new ticker's "Date added" is it.
    best = {}
    for o, (n, begin) in sorted(out.items()):
        gap = abs((begin - added[n]).days)
        if n not in best or gap < best[n][1]:
            best[n] = (o, gap)
    return {o: n for n, (o, _) in best.items()}


def _name_tokens(s):
    s = re.sub(r"[^a-z0-9 ]", " ", str(s).lower().replace("'", ""))
    stop = {"inc", "corp", "corporation", "co", "company", "the", "ltd", "plc", "group",
            "holdings", "holding", "class", "a", "b", "c", "com", "new", "de", "and"}
    return {w for w in s.split() if w not in stop}


def names_match(a, b):
    """Same company name, give or take suffixes ("Moody's Corp" ~ "MOODYS CORP /DE/")."""
    ta, tb = _name_tokens(a), _name_tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.5


def resolve_tickers(tickers, hist, cur, cur_old, changes, sec_map):
    """Historical ticker -> (CIK, today's ticker, how it was found).

    1. Wikipedia constituent tables carry each company's CIK.
    2. A renamed ticker follows its rename chain to the current symbol.
    3. A removed ticker whose name is in the change log takes the CIK of the
       SEC company with that ticker only if the names agree (symbols get reused).
    4. Otherwise the SEC ticker is accepted provisionally ("sec_unverified");
       run.py drops it unless that company was filing before it joined.
    """
    wiki = {}
    for t in (cur_old, cur):                       # today's table wins
        for r in t.itertuples():
            if pd.notna(getattr(r, "CIK", None)):
                wiki[r.Symbol] = int(r.CIK)
    names = {}
    for r in changes.itertuples():
        if r.removed:
            names.setdefault(r.removed, r.removed_name)
        if r.added:
            names.setdefault(r.added, r.added_name)
    added = {}
    for t in (cur_old, cur):
        for sym, d in zip(t["Symbol"], pd.to_datetime(t.get("Date added"), errors="coerce")):
            if pd.notna(d):
                added[sym] = d
    renames = find_renames(hist, changes, added)
    sec = sec_map.drop_duplicates("ticker").set_index("ticker")
    by_cik = sec_map.groupby("cik")["ticker"].first().to_dict()

    out = {}
    for t in tickers:
        final, seen = t, {t}
        while final in renames and renames[final] not in seen:
            final = renames[final]
            seen.add(final)
        how = "renamed" if final != t else ""
        if final in wiki:
            cik = wiki[final]
            out[t] = (cik, by_cik.get(cik, final), how or "wikipedia")
        elif final in sec.index:
            cik, title = int(sec.at[final, "cik"]), sec.at[final, "title"]
            if t in names and not names_match(names[t], title):
                continue                           # same symbol, different company
            out[t] = (cik, final, how or ("name" if t in names else "sec_unverified"))
    return out
