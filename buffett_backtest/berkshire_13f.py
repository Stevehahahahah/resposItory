"""Every 13F that Berkshire Hathaway has filed: holdings by quarter and new buys.

13F filings list the US stocks Berkshire owns at each quarter end, filed up to
45 days later.  Some positions are kept confidential at first and disclosed
later in a 13F-HR/A that "adds new holdings"; those count from the day the
amendment was filed.  Since 2013 the holdings table is XML, before that a
fixed-width text table.  Values are in thousands of dollars until filings made
on or after 2023-01-03, which report whole dollars.
"""

import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from lxml import etree

import data

BRK_CIK = 1067983
DOLLARS_FROM = pd.Timestamp("2023-01-03")
ROOT = Path(__file__).resolve().parent
CUSIP_MAP = ROOT / "cusip_map.csv"

CUSIP_RE = re.compile(r"(?<![0-9A-Z])([0-9]{3}[0-9A-Z]{3})[ -]?([0-9A-Z]{2})[ -]?([0-9])(?![0-9A-Z])")
NUM_RE = re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?![\d,])|(?<![\d,.])\d+(?![\d,.])")


def filing_list():
    sub = data.submissions(BRK_CIK)
    t = sub["filing_table"]
    t = t[t["form"].isin(["13F-HR", "13F-HR/A"])].copy()
    t["filingDate"] = pd.to_datetime(t["filingDate"])
    return t.sort_values("filingDate").reset_index(drop=True)


def _documents(txt):
    """(type, body) of each <DOCUMENT> in a full EDGAR submission."""
    for m in re.finditer(r"<DOCUMENT>(.*?)</DOCUMENT>", txt, re.S | re.I):
        doc = m.group(1)
        t = re.search(r"<TYPE>([^\n<]+)", doc, re.I)
        body = re.search(r"<TEXT>(.*)</TEXT>", doc, re.S | re.I)
        yield (t.group(1).strip().upper() if t else ""), (body.group(1) if body else doc)


def _xml(body):
    m = re.search(r"<XML>(.*)</XML>", body, re.S | re.I)
    if not m:
        return None
    raw = m.group(1).strip().encode()
    try:
        return etree.fromstring(raw, etree.XMLParser(recover=True, huge_tree=True))
    except etree.XMLSyntaxError:
        return None


def _x(node, name):
    r = node.xpath(f".//*[local-name()='{name}']")
    return r[0].text.strip() if r and r[0].text else None


def _num(s):
    return float(s.replace(",", "")) if s else 0.0


def parse_xml_table(root):
    rows = []
    for it in root.xpath(".//*[local-name()='infoTable']"):
        if _x(it, "putCall") or (_x(it, "sshPrnamtType") or "SH").upper() != "SH":
            continue
        rows.append({"cusip": (_x(it, "cusip") or "").upper(), "name": _x(it, "nameOfIssuer"),
                     "value": _num(_x(it, "value")), "shares": _num(_x(it, "sshPrnamt"))})
    return rows


def parse_text_table(body):
    """Fixed-width tables of the 1999-2013 filings.

    A row names the issuer and CUSIP, then value (thousands) and shares.
    Following lines that start with a number continue the same issuer (the
    same stock held by another Berkshire subsidiary).
    """
    rows, cur = [], None
    for line in body.splitlines():
        if re.search(r"\b(PUT|CALL|PRN)\b", line):
            continue
        m = CUSIP_RE.search(line)
        if m:
            nums = NUM_RE.findall(line[m.end():])
            if len(nums) < 2:
                cur = None
                continue
            cur = {"cusip": "".join(m.groups()), "name": line[:m.start()].strip()}
            rows.append({**cur, "value": _num(nums[0]), "shares": _num(nums[1])})
        elif cur and re.match(r"\s+\d", line):
            nums = NUM_RE.findall(line)
            if len(nums) >= 2:
                rows.append({**cur, "value": _num(nums[0]), "shares": _num(nums[1])})
        elif line.strip() and not re.match(r"\s", line):
            cur = None
    for r in rows:                                   # strip trailing class words from the name
        r["name"] = re.sub(r"\s{2,}.*$", "", r["name"])
    return rows


def parse_submission(txt):
    """Header facts and holdings rows of one 13F submission."""
    head = txt[:5000]
    period = re.search(r"CONFORMED PERIOD OF REPORT:\s*(\d{8})", head)
    filed = re.search(r"FILED AS OF DATE:\s*(\d{8})", head)
    form = re.search(r"CONFORMED SUBMISSION TYPE:\s*(\S+)", head)
    out = {"period": pd.to_datetime(period.group(1)) if period else None,
           "filed": pd.to_datetime(filed.group(1)) if filed else None,
           "form": form.group(1) if form else None, "amendment": None,
           "cover_total": None, "rows": []}
    for typ, body in _documents(txt):
        root = _xml(body)
        if typ.startswith("13F-HR") and root is not None:
            out["amendment"] = (_x(root, "amendmentType") or "").upper() or None
            tot = _x(root, "tableValueTotal")
            out["cover_total"] = _num(tot) if tot else None
        elif typ.startswith("13F-HR") or typ.startswith("13F-NT"):
            if re.search(r"\[\s*[xX]\s*\]\s*adds new holdings", body):
                out["amendment"] = "NEW HOLDINGS"
            elif re.search(r"\[\s*[xX]\s*\]\s*is a restatement", body):
                out["amendment"] = "RESTATEMENT"
            tot = re.search(r"Value Total:?\s*\$?\s*([\d,]+)", body, re.I)
            out["cover_total"] = _num(tot.group(1)) if tot else None
        if "INFORMATION TABLE" in typ or typ.startswith("13F-HR"):
            out["rows"] += parse_xml_table(root) if root is not None else []
            if root is None and ("INFORMATION TABLE" in typ or not out["rows"]):
                out["rows"] += parse_text_table(body)
    if out["form"] == "13F-HR/A" and out["amendment"] is None and out["rows"]:
        out["amendment"] = "RESTATEMENT"
    return out


def all_filings():
    """One row per (filing, CUSIP): period, filed, form, amendment, value ($), shares."""
    recs, checks = [], []
    for _, f in filing_list().iterrows():
        txt = data.sec_full_submission(BRK_CIK, f["accessionNumber"])
        if txt is None:
            print(f"  missing {f['accessionNumber']}", file=sys.stderr)
            continue
        p = parse_submission(txt)
        filed = p["filed"] or f["filingDate"]
        period = p["period"] if p["period"] is not None else pd.to_datetime(f.get("reportDate"))
        mult = 1.0 if filed >= DOLLARS_FROM else 1000.0
        df = pd.DataFrame(p["rows"], columns=["cusip", "name", "value", "shares"])
        g = df.groupby("cusip").agg(name=("name", "first"), value=("value", "sum"), shares=("shares", "sum"))
        for cusip, r in g.iterrows():
            recs.append({"accession": f["accessionNumber"], "period": period, "filed": filed,
                         "form": p["form"] or f["form"], "amendment": p["amendment"], "cusip": cusip,
                         "name": r["name"], "value": r["value"] * mult, "shares": r["shares"]})
        checks.append({"accession": f["accessionNumber"], "period": period, "filed": filed,
                       "form": p["form"] or f["form"], "amendment": p["amendment"], "rows": len(g),
                       "table_total": df["value"].sum(), "cover_total": p["cover_total"]})
    return pd.DataFrame(recs), pd.DataFrame(checks)


def known_positions(h, period, asof):
    """Holdings for one quarter as known on asof: the newest full report plus later additions."""
    q = h[(h["period"] == period) & (h["filed"] <= asof)]
    full = q[q["amendment"].isna() | (q["amendment"] == "RESTATEMENT")]
    if full.empty:
        return q.iloc[0:0]
    base = full[full["filed"] == full["filed"].max()]
    adds = q[(q["amendment"] == "NEW HOLDINGS") & ~q["cusip"].isin(base["cusip"])]
    return pd.concat([base, adds])


def final_positions(h):
    """Holdings of every quarter with everything that was eventually disclosed."""
    return {p: known_positions(h, p, h["filed"].max()) for p in sorted(h["period"].unique())}


def new_buys(h, cmap):
    """Each time a stock appears that was not held the quarter before.

    known = the filing date that first disclosed it.  Ticker-level, so a CUSIP
    change after a corporate action is not mistaken for a purchase.
    """
    h = h.assign(ticker=h["cusip"].map(cmap))
    final = final_positions(h)
    periods = sorted(final)
    out = []
    for prev, cur in zip(periods, periods[1:]):
        before = set(final[prev].assign(ticker=lambda d: d["cusip"].map(cmap))["ticker"].dropna())
        now = final[cur].assign(ticker=lambda d: d["cusip"].map(cmap))
        for t, g in now.dropna(subset=["ticker"]).groupby("ticker"):
            if t in before:
                continue
            first = h[(h["period"] == cur) & (h["ticker"] == t)]["filed"].min()
            out.append({"ticker": t, "period": cur, "known": first, "name": g["name"].iloc[0],
                        "value": g["value"].sum()})
    return pd.DataFrame(out)


# ---------------------------------------------------------------- CUSIP -> ticker

def openfigi(cusips):
    """CUSIP -> exchange ticker via OpenFIGI (free, 10 ids per request without a key)."""
    out = {}
    cusips = list(cusips)
    for i in range(0, len(cusips), 10):
        batch = cusips[i:i + 10]
        body = [{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in batch]
        for _ in range(3):
            r = requests.post("https://api.openfigi.com/v3/mapping", json=body, timeout=60)
            if r.status_code != 429:
                break
            time.sleep(60)
        r.raise_for_status()
        for c, res in zip(batch, r.json()):
            d = (res.get("data") or [{}])[0]
            if d.get("ticker"):
                out[c] = d["ticker"].replace("/", "-").replace(".", "-").upper()
        time.sleep(2.5)                                  # 25 requests a minute without a key
    return out


def build_cusip_map(h, sec_map):
    """Extend cusip_map.csv with any CUSIP not in it yet.

    Rows already there are kept as they are, so hand corrections survive.
    New rows: OpenFIGI first, otherwise the SEC company whose name matches.
    """
    old = pd.read_csv(CUSIP_MAP, dtype=str) if CUSIP_MAP.exists() else \
        pd.DataFrame(columns=["cusip", "issuer", "ticker", "method", "checked"])
    names = h.sort_values("filed").groupby("cusip")["name"].last()
    todo = [c for c in names.index if c not in set(old["cusip"])]
    try:
        figi = openfigi(todo) if todo else {}
    except Exception as e:                               # OpenFIGI unreachable: names only
        print(f"  OpenFIGI failed ({e}); falling back to name matching", file=sys.stderr)
        figi = {}
    new = []
    for c in todo:
        t, how = figi.get(c), "openfigi"
        if not t:
            hits = [r.ticker for r in sec_map.itertuples() if data.names_match(names[c], r.title)]
            t, how = (hits[0], "name") if len(hits) == 1 else ("", "unmapped")
        new.append({"cusip": c, "issuer": names[c], "ticker": t, "method": how, "checked": ""})
    out = pd.concat([old, pd.DataFrame(new)], ignore_index=True).sort_values("issuer")
    out.to_csv(CUSIP_MAP, index=False)
    return out


def cusip_to_ticker():
    m = pd.read_csv(CUSIP_MAP, dtype=str).fillna("")
    return {r.cusip: r.ticker for r in m.itertuples() if r.ticker}


if __name__ == "__main__":
    h, checks = all_filings()
    out = ROOT / "cache" / "berkshire_13f.csv"
    h.to_csv(out, index=False)
    checks.to_csv(ROOT / "cache" / "berkshire_13f_checks.csv", index=False)
    build_cusip_map(h, data.sec_tickers())
    print(f"{checks.shape[0]} filings, {h['cusip'].nunique()} CUSIPs -> {out}")
