"""Checks of the parsing and accounting logic on small hand-written inputs.

These inputs are made up for testing only; no result in results/ comes from them.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backtest as bt          # noqa: E402
import berkshire_13f as b13    # noqa: E402
import data                    # noqa: E402
import strategy as st          # noqa: E402
from fundamentals import Company  # noqa: E402


def fact(start, end, val, filed, form="10-K"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form, "accn": filed}


def inst(end, val, filed, form="10-K"):
    return {"end": end, "val": val, "filed": filed, "form": form, "accn": filed}


def facts(**concepts):
    gaap = {k: {"units": {"shares" if "Shares" in k else "USD": v}} for k, v in concepts.items()}
    return {"entityName": "Test Co", "facts": {"us-gaap": gaap}}


# ---------------------------------------------------------------- fundamentals

def test_point_in_time_uses_only_filed_facts_and_latest_restatement():
    cf = facts(NetIncomeLoss=[
        fact("2019-01-01", "2019-12-31", 100, "2020-02-20"),
        fact("2019-01-01", "2019-12-31", 90, "2021-02-20"),     # restated in the next 10-K
        fact("2020-01-01", "2020-12-31", 120, "2021-02-20"),
        fact("2020-07-01", "2020-09-30", 30, "2020-10-30", "10-Q"),
    ])
    c = Company(cf)
    assert c.fiscal_year_ends("2020-06-01") == [pd.Timestamp("2019-12-31")]
    s = c.snapshot("2020-06-01")
    assert s["net_income"].tolist() == [100]
    s = c.snapshot("2021-03-01")
    assert s["net_income"].tolist() == [90, 120]
    assert s.attrs["last_filed"] <= pd.Timestamp("2021-03-01")


def test_concept_preference_and_instant_tolerance():
    cf = facts(
        NetIncomeLoss=[fact("2020-01-01", "2020-12-31", 10, "2021-02-01")],
        ProfitLoss=[fact("2020-01-01", "2020-12-31", 12, "2021-02-01")],
        StockholdersEquity=[inst("2021-01-02", 50, "2021-02-01")],     # dated two days later
    )
    s = Company(cf).snapshot("2021-03-01")
    assert s["net_income"].iloc[0] == 10                 # NetIncomeLoss preferred over ProfitLoss
    assert s["equity"].iloc[0] == 50


def test_latest_shares_takes_newest_quarter():
    cf = facts(WeightedAverageNumberOfDilutedSharesOutstanding=[
        fact("2020-01-01", "2020-12-31", 1000, "2021-02-01"),
        fact("2021-01-01", "2021-03-31", 980, "2021-05-01", "10-Q"),
        fact("2021-01-01", "2021-06-30", 990, "2021-08-01", "10-Q"),   # year-to-date
        fact("2021-04-01", "2021-06-30", 970, "2021-08-01", "10-Q"),
    ])
    c = Company(cf)
    assert c.latest_shares("2021-07-01") == (980, pd.Timestamp("2021-05-01"))
    assert c.latest_shares("2021-09-01") == (970, pd.Timestamp("2021-08-01"))


# ---------------------------------------------------------------- splits, DCF, metrics

def test_split_factor_between():
    sp = pd.Series({pd.Timestamp("2014-06-09"): 7.0, pd.Timestamp("2020-08-31"): 4.0})
    assert data.split_factor_between(sp, "2014-01-01", "2100-01-01") == 28.0
    assert data.split_factor_between(sp, "2020-08-31", "2100-01-01") == 1.0
    assert data.split_factor_between(sp, "2019-12-31", "2020-08-30") == 1.0


def test_dcf_closed_form():
    # growth equal to the discount rate: ten years of 1, then 1.03 / 0.07
    assert st.dcf(1.0, 0.10, 0.10, 0.03, 10) == pytest.approx(10 + 1.03 / 0.07)
    assert st.dcf(1.0, 0.0, 0.10, 0.0, 10) == pytest.approx(10.0)       # perpetuity of 1 at 10%


def snapshot(ni, eq, debt, da, capex, shares, divs=None, start=2015):
    ends = pd.to_datetime([f"{start + i}-12-31" for i in range(len(ni))])
    s = pd.DataFrame({"net_income": ni, "equity": eq, "lt_debt": debt, "da": da, "capex": capex,
                      "ocf": np.nan, "revenue": 1000.0, "gross_profit": 400.0,
                      "diluted_shares": shares, "shares_filed": ends + pd.Timedelta(days=40),
                      "dividends": divs if divs is not None else 0.0, "buybacks": 0.0}, index=ends)
    return s


def test_metrics_and_rules_on_a_wonderful_cheap_business():
    s = snapshot(ni=[100, 110, 121, 133, 146, 161], eq=[500, 520, 540, 560, 580, 600], debt=[100] * 6,
                 da=[20] * 6, capex=[20] * 6, shares=[100] * 6, divs=[90] * 6)
    days = pd.bdate_range("2014-01-01", "2021-04-01")
    px = pd.Series(np.linspace(4.0, 10.0, len(days)), index=days)    # value grows with retained earnings
    m = st.metrics(s, px, pd.Series(dtype=float), 100, pd.Timestamp("2021-02-01"), "2021-04-01")
    assert m["roe_avg"] > 0.2 and m["growth"] == pytest.approx(0.10, abs=1e-3)
    assert m["market_cap"] == pytest.approx(1000)
    assert st.failures(m, st.DEFAULTS) == []
    assert m["mos"] > 0.25 and st.buyable(m, st.DEFAULTS)


def test_split_after_filing_does_not_fake_a_bargain():
    s = snapshot(ni=[100] * 6, eq=[500] * 6, debt=[0] * 6, da=[0] * 6, capex=[0] * 6, shares=[100] * 6)
    px = pd.Series(2.5, index=pd.bdate_range("2014-01-01", "2021-04-01"))   # today's basis after a 4:1 split
    splits = pd.Series({pd.Timestamp("2021-03-01"): 4.0})
    m = st.metrics(s, px, splits, 100, pd.Timestamp("2021-02-01"), "2021-04-01")
    assert m["market_cap"] == pytest.approx(2.5 * 400)                       # = 10 x 100 before the split


def test_dollar_test_fails_when_retained_earnings_add_no_value():
    s = snapshot(ni=[100] * 6, eq=[500] * 6, debt=[0] * 6, da=[0] * 6, capex=[0] * 6, shares=[100] * 6)
    px = pd.Series(10.0, index=pd.bdate_range("2014-01-01", "2021-04-01"))   # flat price, nothing paid out
    m = st.metrics(s, px, pd.Series(dtype=float), 100, pd.Timestamp("2021-02-01"), "2021-04-01")
    assert m["dollar_test"] == 0 and "dollar_test" in st.failures(m, st.DEFAULTS)


def test_rules_reject_debt_and_dilution():
    s = snapshot(ni=[100] * 6, eq=[500] * 6, debt=[1000] * 6, da=[0] * 6, capex=[0] * 6,
                 shares=[100, 104, 108, 112, 116, 120])
    px = pd.Series(1.0, index=pd.bdate_range("2014-01-01", "2021-04-01"))
    m = st.metrics(s, px, pd.Series(dtype=float), 120, pd.Timestamp("2021-02-01"), "2021-04-01")
    bad = st.failures(m, st.DEFAULTS)
    assert "debt" in bad and "dilution" in bad and "no_growth" in bad


def test_calibrate_needs_enough_buys():
    buys = pd.DataFrame({"known": pd.to_datetime(["2012-01-01"] * 10 + ["2030-01-01"]),
                         "roe_avg": np.linspace(0.1, 0.3, 11), "roe_min": 0.08,
                         "debt_years": 2.0, "mos": -0.2})
    th, n = st.calibrate(buys, "2011-01-01")
    assert n == 0 and th == st.DEFAULTS
    th, n = st.calibrate(buys, "2020-01-01")
    assert n == 10 and th["mos"] == pytest.approx(-0.2) and th["roe_floor"] == pytest.approx(0.08)


# ---------------------------------------------------------------- 13F parsing

OLD_TEXT = """<SEC-HEADER>
CONFORMED SUBMISSION TYPE:	13F-HR
CONFORMED PERIOD OF REPORT:	20081231
FILED AS OF DATE:		20090217
</SEC-HEADER>
<DOCUMENT>
<TYPE>13F-HR
<TEXT>
Form 13F Information Table Value Total:   $ 1,300 (thousands)

                                                  Column 4   Column 5
Name of Issuer          Title of Class  CUSIP     Value      Shares
American Express Co.    Com             025816 10 9    1,000     50,000     X    4, 2      50,000
                                                         200     10,000     X    4         10,000
Coca Cola Co.           Com             191216100        100      2,000     X    1          2,000
Some Co PUT             Com             123456789         50      1,000     X    1
                                                        ----
                                                       1,300
</TEXT>
</DOCUMENT>
"""

XML_TEXT = """<SEC-HEADER>
CONFORMED SUBMISSION TYPE:	13F-HR/A
CONFORMED PERIOD OF REPORT:	20200930
FILED AS OF DATE:		20201116
</SEC-HEADER>
<DOCUMENT>
<TYPE>13F-HR/A
<TEXT>
<XML>
<edgarSubmission xmlns="http://www.sec.gov/edgar/thirteenffiler"><formData><coverPage>
<isAmendment>true</isAmendment><amendmentInfo><amendmentType>NEW HOLDINGS</amendmentType></amendmentInfo>
</coverPage><summaryPage><tableValueTotal>8600000</tableValueTotal></summaryPage></formData></edgarSubmission>
</XML>
</TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>INFORMATION TABLE
<TEXT>
<XML>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
<infoTable><nameOfIssuer>VERIZON COMMUNICATIONS INC</nameOfIssuer><titleOfClass>COM</titleOfClass>
<cusip>92343V104</cusip><value>8600000</value><shrsOrPrnAmt><sshPrnamt>146716496</sshPrnamt>
<sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
<infoTable><nameOfIssuer>X CORP</nameOfIssuer><cusip>000000000</cusip><value>5</value>
<shrsOrPrnAmt><sshPrnamt>1</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall>Put</putCall></infoTable>
</informationTable>
</XML>
</TEXT>
</DOCUMENT>
"""


def test_parse_old_text_filing_with_continuation_lines():
    p = b13.parse_submission(OLD_TEXT)
    assert p["period"] == pd.Timestamp("2008-12-31") and p["filed"] == pd.Timestamp("2009-02-17")
    rows = pd.DataFrame(p["rows"])
    g = rows.groupby("cusip")[["value", "shares"]].sum()
    assert g.loc["025816109"].tolist() == [1200, 60000]
    assert g.loc["191216100"].tolist() == [100, 2000]
    assert "123456789" not in g.index                     # puts are skipped
    assert p["cover_total"] == 1300 and g["value"].sum() == 1300


def test_parse_xml_amendment():
    p = b13.parse_submission(XML_TEXT)
    assert p["amendment"] == "NEW HOLDINGS" and p["cover_total"] == 8600000
    assert [r["cusip"] for r in p["rows"]] == ["92343V104"]


def test_known_positions_adds_confidential_holdings_when_disclosed():
    q = pd.Timestamp("2020-09-30")
    h = pd.DataFrame([
        {"period": q, "filed": pd.Timestamp("2020-11-16"), "amendment": None, "cusip": "A", "value": 1.0},
        {"period": q, "filed": pd.Timestamp("2021-02-16"), "amendment": "NEW HOLDINGS", "cusip": "B", "value": 2.0},
    ])
    assert set(b13.known_positions(h, q, pd.Timestamp("2020-12-01"))["cusip"]) == {"A"}
    assert set(b13.known_positions(h, q, pd.Timestamp("2021-03-01"))["cusip"]) == {"A", "B"}


def test_new_buys_by_ticker():
    rows = []
    for p, f, holds in [("2019-12-31", "2020-02-14", ["OLD1"]), ("2020-03-31", "2020-05-15", ["OLD1", "NEWC"])]:
        for c in holds:
            rows.append({"period": pd.Timestamp(p), "filed": pd.Timestamp(f), "amendment": None,
                         "cusip": c, "name": c, "value": 1.0})
    h = pd.DataFrame(rows)
    b = b13.new_buys(h, {"OLD1": "AAA", "NEWC": "AAA"})              # CUSIP change, same company
    assert b.empty
    b = b13.new_buys(h, {"OLD1": "AAA", "NEWC": "BBB"})
    assert b["ticker"].tolist() == ["BBB"] and b["known"].iloc[0] == pd.Timestamp("2020-05-15")


# ---------------------------------------------------------------- S&P membership, Yahoo parsing

def _hist(rows):
    return pd.Series({pd.Timestamp(d): set(t) for d, t in rows}).sort_index()


def test_sp500_members_takes_last_list_on_or_before():
    hist = _hist([("2015-01-02", ["AAA", "OLD"]), ("2018-01-02", ["AAA", "NEW"])])
    assert data.sp500_members("2017-12-31", hist) == {"AAA", "OLD"}
    assert data.sp500_members("2018-01-02", hist) == {"AAA", "NEW"}
    assert data.sp500_members("2014-01-01", hist) == set()


def test_renames_need_original_join_date_and_no_listed_change():
    hist = _hist([("2013-12-23", ["FB", "KEEP"]),
                  ("2015-01-02", ["FB", "XOLD", "KEEP"]),
                  ("2022-06-09", ["META", "XNEW", "KEEP"])])
    changes = pd.DataFrame({"date": [pd.Timestamp("2022-06-09")], "added": ["XNEW"], "removed": ["XOLD"]})
    added = {"META": pd.Timestamp("2013-12-23"), "XNEW": pd.Timestamp("2022-06-09"), "KEEP": pd.Timestamp("2000-01-01")}
    assert data.find_renames(hist, changes, added) == {"FB": "META"}
    # without the change-log entry: XNEW joined after XOLD did, and META's join date is FB's, not XOLD's
    assert data.find_renames(hist, changes.iloc[0:0], added) == {"FB": "META"}


def test_resolve_tickers_rejects_reused_symbols():
    hist = _hist([("2015-01-02", ["FB", "GONE"]), ("2022-06-09", ["META"])])
    cur = pd.DataFrame({"Symbol": ["META"], "CIK": [1326801], "Date added": ["2013-12-23"]})
    changes = pd.DataFrame({"date": [pd.Timestamp("2022-06-09")], "added": [None], "removed": ["GONE"],
                            "added_name": [None], "removed_name": ["Gone Stores Inc"]})
    sec = pd.DataFrame({"ticker": ["META", "GONE"], "cik": [1326801, 999], "title": ["Meta Platforms", "Gone Mining Ltd"]})
    r = data.resolve_tickers(["FB", "GONE", "META"], hist, cur, cur, changes, sec)
    assert r["FB"] == (1326801, "META", "renamed") and r["META"][2] == "wikipedia"
    assert "GONE" not in r


def test_parse_yahoo_chart():
    res = {"meta": {"gmtoffset": -14400}, "timestamp": [1598880600, 1598967000],
           "indicators": {"quote": [{"close": [129.04, 134.18]}], "adjclose": [{"adjclose": [126.6, 131.6]}]},
           "events": {"splits": {"1598880600": {"date": 1598880600, "numerator": 4, "denominator": 1}}}}
    prices, splits = data.parse_yahoo_chart(res)
    assert list(prices.index) == [pd.Timestamp("2020-08-31"), pd.Timestamp("2020-09-01")]
    assert splits.loc["2020-08-31"] == 4.0


def test_names_match():
    assert data.names_match("MOODYS CORP", "Moody's Corp")
    assert data.names_match("Moody's Corporation", "MOODYS CORP /DE/")
    assert not data.names_match("Gone Stores Inc", "Gone Mining Ltd")
    assert not data.names_match("APPLE INC", "Applied Materials Inc")


# ---------------------------------------------------------------- portfolio accounting

def test_book_accounting_with_costs():
    cal = pd.bdate_range("2020-01-01", periods=5)
    adj = pd.DataFrame({"X": [10, 11, 12, 12, 15], "BIL": [1.0] * 5}, index=cal, dtype=float)
    b = bt.Book(adj, adj["BIL"], cal[0])
    b.mark(cal[1])
    b.buy("X", cal[1], 0.5)
    assert b.value(cal[1]) == pytest.approx(1 - 0.5 * bt.COST)
    b.mark(cal[4])
    b.sell("X", cal[4], "test")
    b.mark(cal[4], inclusive=True)
    units = 0.5 * (1 - bt.COST) / 11
    expected = 0.5 + units * 15 * (1 - bt.COST)
    r = b.result("t")
    assert r["curve"].iloc[-1] == pytest.approx(expected)
    assert r["curve"].loc[cal[3]] == pytest.approx(0.5 + units * 12)
    assert list(r["curve"].index) == list(cal)


def test_rebalance_reaches_target_weights():
    cal = pd.bdate_range("2020-01-01", periods=3)
    adj = pd.DataFrame({"X": [1.0, 1, 1], "Y": [1.0, 1, 1], "BIL": [1.0, 1, 1]}, index=cal)
    b = bt.Book(adj, adj["BIL"], cal[0])
    b.rebalance({"X": 0.6, "Y": 0.3}, cal[0])
    v = b.value(cal[0])
    assert b.units["X"] / v == pytest.approx(0.6, abs=0.01) and b.units["Y"] / v == pytest.approx(0.3, abs=0.01)
    b.rebalance({"Y": 0.5}, cal[1])
    assert "X" not in b.units


def test_stats_and_yearly():
    idx = pd.bdate_range("2020-01-01", "2021-12-31")
    curve = pd.Series(np.linspace(1, 1.21, len(idx)), index=idx)
    cash = pd.Series(1.0, index=idx)
    s = bt.stats(curve, cash)
    assert s["total_return"] == pytest.approx(0.21) and s["max_drawdown"] == 0
    y = bt.yearly(curve)
    assert list(y.index) == [2020, 2021] and (1 + y).prod() == pytest.approx(1.21)
