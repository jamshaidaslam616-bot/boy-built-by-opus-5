"""CFTC Commitments of Traders — weekly positioning, free, since 1986.

Why this series is worth having when the macro drivers turned out to be
contemporaneous-only (see FINDINGS F5): COT is not a price-derived series and it is
not a same-day co-movement. It is *who is holding what*, published on a schedule,
and the documented effect is a slow contrarian one at positioning extremes. Slow,
weekly signals are also the only kind whose edge is not eaten by an $11/lot
open-charge commission.

**The release-timing trap.** The report describes positions as of **Tuesday's**
close but is not published until **Friday 15:30 ET**. Joining it to Tuesday's bar
hands a strategy three days of unpublished information — and because positioning
moves with price, those three days are exactly the ones that would look predictive.
``PUBLICATION_LAG_DAYS`` below is measured from that schedule, not guessed.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

import pandas as pd

from . import _http

HISTORY_URL = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"

# Gold, COMMODITY EXCHANGE INC. The contract code is stable across decades and is
# safer to match on than the market name, which has been reworded.
GOLD_CONTRACT_CODE = "088691"
SILVER_CONTRACT_CODE = "084691"

# Report date is Tuesday; release is Friday 15:30 ET (~19:30-20:30 UTC). Five
# calendar days puts Tuesday's figure in hand by Sunday, so it is available for
# Monday's bar. That forfeits Friday evening, which is immaterial for a weekly
# signal and is the safe direction to be wrong in.
PUBLICATION_LAG_DAYS = 5

_COLUMNS = {
    "Report_Date_as_YYYY-MM-DD": "report_date",
    "CFTC_Contract_Market_Code": "contract_code",
    "Open_Interest_All": "open_interest",
    "Prod_Merc_Positions_Long_All": "producer_long",
    "Prod_Merc_Positions_Short_All": "producer_short",
    "M_Money_Positions_Long_All": "managed_money_long",
    "M_Money_Positions_Short_All": "managed_money_short",
    "Swap_Positions_Long_All": "swap_long",
    "Swap__Positions_Short_All": "swap_short",
}


@dataclass(frozen=True)
class CotSeries:
    contract_code: str
    frame: pd.DataFrame
    """Indexed by report date (Tuesday). Not yet lagged — use ``as_known_on``."""

    publication_lag_days: int = PUBLICATION_LAG_DAYS

    def as_known_on(self, index: pd.DatetimeIndex, columns: list[str] | None = None) -> pd.DataFrame:
        """Values as actually published by each timestamp in ``index``.

        Same discipline as ``macro.MacroSeries.as_known_on``: shift observation
        dates forward by the release lag, then forward-fill. A weekly series held
        flat between releases is correct — nothing new was known in between.
        """
        cols = columns or list(self.frame.columns)
        shifted = self.frame[cols].copy()
        shifted.index = shifted.index + pd.to_timedelta(self.publication_lag_days, unit="D")
        combined = shifted.reindex(shifted.index.union(index)).ffill()
        return combined.reindex(index)


def fetch_year(year: int) -> pd.DataFrame:
    """One year of the disaggregated futures-only report."""
    raw = _http.get(HISTORY_URL.format(year=year))
    archive = zipfile.ZipFile(io.BytesIO(raw))
    with archive.open(archive.namelist()[0]) as handle:
        df = pd.read_csv(handle, low_memory=False)

    missing = [c for c in _COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError(f"CFTC {year}: expected columns absent: {missing}")

    df = df[list(_COLUMNS)].rename(columns=_COLUMNS)
    df["contract_code"] = df["contract_code"].astype(str).str.strip().str.zfill(6)
    df["report_date"] = pd.to_datetime(df["report_date"], utc=True)
    return df


def fetch(contract_code: str, years: range) -> CotSeries:
    """Assemble a contract's history and derive the positioning measures."""
    frames = []
    for year in years:
        try:
            year_df = fetch_year(year)
        except Exception as exc:  # a year not yet published is normal, not fatal
            print(f"  CFTC {year}: skipped ({type(exc).__name__}: {exc})")
            continue
        frames.append(year_df[year_df["contract_code"] == contract_code])

    if not frames:
        raise RuntimeError(f"no CFTC data retrieved for contract {contract_code}")

    df = pd.concat(frames).drop_duplicates(subset="report_date").sort_values("report_date")
    df = df.set_index("report_date").drop(columns=["contract_code"])

    # Net positions. Managed money are the trend-following speculators; producers
    # and merchants are the commercial hedgers who take the other side.
    df["managed_money_net"] = df["managed_money_long"] - df["managed_money_short"]
    df["producer_net"] = df["producer_long"] - df["producer_short"]

    # Scaled by open interest so a position is comparable across a decade in which
    # the market itself grew. A raw contract count confuses growth with conviction.
    df["managed_money_net_pct_oi"] = df["managed_money_net"] / df["open_interest"] * 100.0
    df["producer_net_pct_oi"] = df["producer_net"] / df["open_interest"] * 100.0

    return CotSeries(contract_code=contract_code, frame=df)


def cot_index(net: pd.Series, lookback_weeks: int = 156) -> pd.Series:
    """Where today's positioning sits within its own past range, scaled 0..1.

    The standard construction: ``(x - min) / (max - min)`` over a rolling window,
    three years by convention. Near 1.0 means positioning is as long as it has been
    in three years — which the literature treats as a contrarian SHORT signal, and
    vice versa.

    The window is trailing and inclusive of today only, so no future value enters
    the min or max. That is the easy way to leak here and it is worth stating.
    """
    if lookback_weeks < 20:
        raise ValueError("lookback_weeks below 20 makes the index mostly noise")
    lo = net.rolling(lookback_weeks, min_periods=lookback_weeks).min()
    hi = net.rolling(lookback_weeks, min_periods=lookback_weeks).max()
    span = hi - lo
    # A flat window has no range to place today within; undefined beats 0.5.
    return ((net - lo) / span.where(span > 0)).rename(f"{net.name}_index")
