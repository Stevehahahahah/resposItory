"""Point-in-time annual fundamentals from SEC companyfacts (XBRL).

Each XBRL fact carries the date it was filed.  A snapshot "as of" day t only
ever looks at facts with filed <= t, and for a period reported several times
(original 10-K, then as a comparative in later 10-Ks, or restated) it takes the
latest version that had been filed by t.  That is exactly what an investor
could have read on day t.
"""

import pandas as pd

# Field -> XBRL concepts in order of preference.
DURATION = {
    "net_income": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                "SalesRevenueGoodsNet", "SalesRevenueServicesNet"],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold",
                        "CostOfGoodsSoldExcludingDepreciationDepletionAndAmortization"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsForCapitalImprovements", "PaymentsToAcquireOtherPropertyPlantAndEquipment"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
           "DepreciationAmortizationAndAccretionNet", "Depreciation"],
    "dividends": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "diluted_shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}
INSTANT = {
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "lt_debt": ["LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations",
                "LongTermDebtAndFinanceLeaseObligationsNoncurrent", "LongTermNotesPayable",
                "SeniorLongTermNotes"],
}
ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "10-KT/A", "20-F", "20-F/A", "40-F", "40-F/A"}
PERIODIC_FORMS = ANNUAL_FORMS | {"10-Q", "10-Q/A"}
FIELDS = list(DURATION) + list(INSTANT)


def facts_table(cf):
    """Flatten a companyfacts JSON into one row per (concept, unit, fact)."""
    rows = []
    for tax, concepts in (cf or {}).get("facts", {}).items():
        if tax not in ("us-gaap", "dei", "ifrs-full"):
            continue
        for concept, body in concepts.items():
            for unit, facts in body.get("units", {}).items():
                if unit not in ("USD", "shares"):
                    continue
                for f in facts:
                    rows.append((concept, unit, f.get("start"), f["end"], f["val"],
                                 f.get("form"), f["filed"], f.get("accn")))
    df = pd.DataFrame(rows, columns=["concept", "unit", "start", "end", "val", "form", "filed", "accn"])
    for c in ("start", "end", "filed"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["days"] = (df["end"] - df["start"]).dt.days
    return df


class Company:
    """All fundamentals of one company, queryable as of any date."""

    def __init__(self, cf):
        self.name = (cf or {}).get("entityName", "")
        df = facts_table(cf)
        wanted = {c for v in list(DURATION.values()) + list(INSTANT.values()) for c in v}
        self.df = df[df["concept"].isin(wanted) & df["form"].isin(PERIODIC_FORMS)].copy()

    def _known(self, asof):
        return self.df[self.df["filed"] <= pd.Timestamp(asof)]

    @staticmethod
    def _latest(d, keys):
        """Latest filed version of each fact."""
        return d.sort_values("filed").drop_duplicates(keys, keep="last")

    def fiscal_year_ends(self, asof):
        """Ends of annual periods reported in 10-Ks by asof (from net income facts)."""
        d = self._known(asof)
        d = d[d["form"].isin(ANNUAL_FORMS) & d["days"].between(350, 380)
              & d["concept"].isin(DURATION["net_income"] + DURATION["revenue"])]
        return sorted(d["end"].unique())

    def annual(self, field, asof, ends, with_filed=False):
        """Values of field for each fiscal year end in ends, as known on asof.

        with_filed also returns the filing date of each value, which share
        counts need: a split after that date is not reflected in the number.
        """
        d = self._known(asof)
        out = pd.Series(index=pd.DatetimeIndex(ends), dtype=float)
        filed = pd.Series(index=pd.DatetimeIndex(ends), dtype="datetime64[ns]")
        if field in DURATION:
            concepts = DURATION[field]
            d = d[d["concept"].isin(concepts) & d["days"].between(350, 380)]
            d = self._latest(d, ["concept", "start", "end"])
        else:
            concepts = INSTANT[field]
            d = d[d["concept"].isin(concepts) & d["start"].isna()]
            d = self._latest(d, ["concept", "end"])
        for concept in reversed(concepts):            # preferred concept written last wins
            c = d[d["concept"] == concept].set_index("end")
            c = c[~c.index.duplicated(keep="last")]
            for e in ends:
                e = pd.Timestamp(e)
                if e in c.index:
                    out[e], filed[e] = c.at[e, "val"], c.at[e, "filed"]
                elif field in INSTANT:                # balance sheet dated a few days off
                    near = c[(c.index >= e - pd.Timedelta(days=7)) & (c.index <= e + pd.Timedelta(days=7))]
                    if len(near):
                        out[e], filed[e] = near["val"].iloc[-1], near["filed"].iloc[-1]
        return (out, filed) if with_filed else out

    def latest_shares(self, asof):
        """(diluted share count, filing date) from the newest 10-Q/10-K filed by asof."""
        d = self._known(asof)
        d = d[(d["concept"] == "WeightedAverageNumberOfDilutedSharesOutstanding") & d["days"].between(80, 380)]
        if d.empty:
            return None, None
        d = self._latest(d, ["start", "end"])
        top = d[d["end"] == d["end"].max()]
        top = top.loc[top["days"].idxmin()]               # the quarter, not the year-to-date
        return float(top["val"]), top["filed"]

    def snapshot(self, asof, years=6):
        """Last `years` fiscal years as one DataFrame (index: fiscal year end)."""
        ends = self.fiscal_year_ends(asof)[-years:]
        if not ends:
            return None
        snap = pd.DataFrame({f: self.annual(f, asof, ends) for f in FIELDS if f != "diluted_shares"})
        snap["diluted_shares"], snap["shares_filed"] = self.annual("diluted_shares", asof, ends, with_filed=True)
        gp = snap["gross_profit"]
        snap["gross_profit"] = gp.fillna(snap["revenue"] - snap["cost_of_revenue"])
        snap.attrs["asof"] = pd.Timestamp(asof)
        snap.attrs["last_filed"] = self._known(asof)["filed"].max()
        assert snap.attrs["last_filed"] <= pd.Timestamp(asof), "look-ahead: fact filed after asof"
        return snap
