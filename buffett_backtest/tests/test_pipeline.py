"""Runs run.py end to end with every download replaced by synthetic data.

This only checks that the pieces fit together; the numbers mean nothing.
"""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import berkshire_13f as b13   # noqa: E402
import data                   # noqa: E402
import run                    # noqa: E402

TICKERS = ["AAA", "BBB", "CCC", "DDD", "BANK"]


def fake_facts(cik):
    rng = np.random.default_rng(cik)
    ni0 = 100 + 50 * rng.random()
    g = 0.02 + 0.08 * rng.random()
    facts = {k: [] for k in ("NetIncomeLoss", "StockholdersEquity", "LongTermDebt", "DepreciationAndAmortization",
                             "PaymentsToAcquirePropertyPlantAndEquipment", "Revenues", "GrossProfit",
                             "WeightedAverageNumberOfDilutedSharesOutstanding", "PaymentsOfDividends")}
    for y in range(2008, 2026):
        st, en, filed = f"{y}-01-01", f"{y}-12-31", f"{y + 1}-02-20"
        ni = ni0 * (1 + g) ** (y - 2008)
        dur = lambda v: {"start": st, "end": en, "val": v, "filed": filed, "form": "10-K", "accn": filed}  # noqa: E731
        facts["NetIncomeLoss"].append(dur(ni))
        facts["Revenues"].append(dur(ni * 5))
        facts["GrossProfit"].append(dur(ni * 2))
        facts["DepreciationAndAmortization"].append(dur(ni * 0.2))
        facts["PaymentsToAcquirePropertyPlantAndEquipment"].append(dur(ni * 0.25))
        facts["PaymentsOfDividends"].append(dur(ni * 0.5))
        facts["WeightedAverageNumberOfDilutedSharesOutstanding"].append(dur(100.0))
        facts["StockholdersEquity"].append({"end": en, "val": ni * 4, "filed": filed, "form": "10-K", "accn": filed})
        facts["LongTermDebt"].append({"end": en, "val": ni * (1 + 4 * rng.random()), "filed": filed,
                                      "form": "10-K", "accn": filed})
    return {"entityName": f"Co {cik}", "facts": {"us-gaap": {
        k: {"units": {"shares" if "Shares" in k else "USD": v}} for k, v in facts.items()}}}


def fake_chart(symbol, start, end):
    idx = pd.bdate_range("2004-01-01", end)
    rng = np.random.default_rng(abs(hash(symbol)) % 2 ** 32)
    drift = 0.00003 if symbol == "BIL" else 0.0003
    vol = 0.0005 if symbol == "BIL" else 0.015
    p = 20 * np.exp(np.cumsum(rng.normal(drift, vol, len(idx))))
    df = pd.DataFrame({"close": p, "adjclose": p}, index=idx)
    return df, pd.Series(dtype=float)


def test_run_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "CACHE", tmp_path / "cache")
    (tmp_path / "cache").mkdir()
    monkeypatch.setattr(run, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(data, "yahoo_chart", fake_chart)
    cur = pd.DataFrame({"Symbol": TICKERS[:4] + ["BANK"], "CIK": [1, 2, 3, 4, 5],
                        "Date added": ["2000-01-01"] * 3 + ["2018-06-01", "2000-01-01"]})
    ch = pd.DataFrame({"date": pd.to_datetime(["2018-06-01"]), "added": ["DDD"], "removed": ["OLDX"],
                       "added_name": ["d"], "removed_name": ["Old X Inc"]})
    hist = pd.Series({pd.Timestamp("2010-01-04"): {"AAA", "BBB", "CCC", "OLDX", "BANK"},
                      pd.Timestamp("2018-06-01"): {"AAA", "BBB", "CCC", "DDD", "BANK"},
                      pd.Timestamp("2025-08-01"): {"AAA", "BBB", "CCC", "DDD", "BANK"}})
    monkeypatch.setattr(data, "sp500_history", lambda: hist)
    monkeypatch.setattr(data, "sp500_wikipedia", lambda: (cur, cur, ch))
    monkeypatch.setattr(data, "sec_tickers", lambda: pd.DataFrame(
        {"ticker": TICKERS + ["OLDX"], "cik": [1, 2, 3, 4, 5, 6], "title": ["a", "b", "c", "d", "bank", "Old X Inc"]}))
    monkeypatch.setattr(data, "companyfacts", fake_facts)
    monkeypatch.setattr(data, "submissions", lambda cik: {"sic": "6022" if cik == 5 else "2000"})

    rows = []
    for q in pd.date_range("2010-03-31", "2025-06-30", freq="QE"):
        held = ["C1", "C2"] + (["C3"] if q.year >= 2016 else [])
        for i, c in enumerate(held):
            rows.append({"accession": str(q.date()), "period": q, "filed": q + pd.Timedelta(days=45), "form": "13F-HR",
                         "amendment": None, "cusip": c, "name": c, "value": 100.0 * (i + 1), "shares": 1.0})
    h = pd.DataFrame(rows)
    checks = pd.DataFrame({"accession": h["accession"].unique(), "cover_total": np.nan, "table_total": 1.0})
    monkeypatch.setattr(b13, "all_filings", lambda: (h, checks))
    monkeypatch.setattr(b13, "build_cusip_map", lambda h, m: None)
    monkeypatch.setattr(b13, "cusip_to_ticker", lambda: {"C1": "AAA", "C2": "BBB", "C3": "CCC"})
    monkeypatch.setattr(sys, "argv", ["run.py", "--start", "2015-01-01", "--end", "2025-09-30"])

    run.main()
    out = tmp_path / "results"
    summary = pd.read_csv(out / "summary.csv", index_col=0)
    assert {"B n=10", "C copy Berkshire 13F", "SPY buy & hold"} <= set(summary.index)
    assert (out / "equity_curve.png").exists() and (out / "summary.md").exists()
    cov = pd.read_csv(out / "coverage.csv")
    assert (cov["screened"] <= 4).all()                    # the bank is excluded
    assert summary["end"].iloc[0] >= "2025-09"
    assert date.fromisoformat(summary.loc["SPY buy & hold", "start"]) >= date(2015, 1, 1)
