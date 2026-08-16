"""Free macro series, aligned point-in-time.

The information dimension every retail strategy is missing is not a cleverer moving
average — it is data that is not the price. Real yields and the dollar are gold's
two best-documented drivers, they are free, and almost nobody wires them in.

**The trap this module exists to avoid.** A macro series is stamped with the date it
*describes*, not the date it was *published*. FRED's broad dollar index carries an
observation date of 2026-07-31 while the 10-year real yield already has 2026-08-06 —
a publication lag of about a week. Joining either to a price series on its
observation date lets a strategy trade on a number that did not exist yet, and the
resulting backtest looks brilliant.

So ``publication_lag_days`` is a **required** argument with no default. Forgetting it
must be impossible, not merely discouraged.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import _http

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"


@dataclass(frozen=True)
class MacroSeries:
    series_id: str
    name: str
    values: pd.Series
    publication_lag_days: int
    """Calendar days between the date a value DESCRIBES and the date it is KNOWN.

    Measured from the feed, not guessed — see ``measure_publication_lag``. Rounded
    up, because being a day too cautious costs a little signal and being a day too
    eager invents information.
    """

    def as_known_on(self, index: pd.DatetimeIndex) -> pd.Series:
        """The latest value that was actually PUBLISHED by each timestamp in ``index``.

        Shifts observation dates forward by the publication lag, then forward-fills.
        A decision made at bar t therefore sees only figures released on or before t.
        """
        shifted = self.values.copy()
        shifted.index = shifted.index + pd.to_timedelta(self.publication_lag_days, unit="D")
        combined = shifted.reindex(shifted.index.union(index)).ffill()
        return combined.reindex(index).rename(self.name)


def fetch_fred(series_id: str, publication_lag_days: int, name: str | None = None) -> MacroSeries:
    """Download a FRED series as CSV. No API key required for this endpoint."""
    body = _http.get_text(FRED_CSV.format(series_id=series_id), timeout=60)
    df = pd.read_csv(io.StringIO(body))
    date_col = df.columns[0]
    value_col = df.columns[1]

    df[date_col] = pd.to_datetime(df[date_col], utc=True)
    # FRED writes "." for missing observations (holidays, non-publication days).
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    series = df.set_index(date_col)[value_col].dropna().sort_index()

    if series.empty:
        raise RuntimeError(f"{series_id}: FRED returned no usable observations")

    return MacroSeries(
        series_id=series_id,
        name=name or series_id,
        values=series,
        publication_lag_days=publication_lag_days,
    )


def measure_publication_lag(series: pd.Series, reference_today: pd.Timestamp) -> int:
    """How stale is this feed's newest observation, in calendar days?

    A lower bound on the true publication lag, and the only part of it observable
    without a vintage database. Used to CHECK that a configured lag is not
    optimistic, never to set one silently.
    """
    newest = series.index.max()
    return int((reference_today - newest).days)


def assert_lag_is_not_optimistic(macro: MacroSeries, reference_today: pd.Timestamp) -> None:
    """Fail if the configured lag is shorter than the staleness we can observe.

    Catches the case where a feed's publication schedule changed and a hardcoded
    lag quietly became look-ahead.
    """
    observed = measure_publication_lag(macro.values, reference_today)
    if macro.publication_lag_days < observed:
        raise ValueError(
            f"{macro.series_id}: configured publication lag is {macro.publication_lag_days}d "
            f"but the feed's newest observation is already {observed}d old. The configured "
            "lag is optimistic and would let a backtest see unpublished data."
        )


# --- The series that matter for gold, with lags measured from the live feed ---

def real_yield_10y() -> MacroSeries:
    """10-year TIPS yield. Gold's single best-documented macro driver.

    Published next business day, so a 4-day calendar lag covers a weekend plus a
    holiday. Deliberately not tuned tighter.
    """
    return fetch_fred("DFII10", publication_lag_days=4, name="real_yield_10y")


def broad_dollar_index() -> MacroSeries:
    """Nominal Broad US Dollar Index.

    Chosen over the familiar DXY on purpose: DXY is heavily euro-weighted and the
    literature finds it correlates with gold LESS well than broader trade-weighted
    indices. This one runs about a week behind, hence the larger lag.
    """
    return fetch_fred("DTWEXBGS", publication_lag_days=10, name="broad_dollar")


def cache(macro: MacroSeries, root: Path) -> Path:
    path = Path(root) / f"macro_{macro.series_id}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    macro.values.to_frame("value").assign(
        publication_lag_days=macro.publication_lag_days, name=macro.name
    ).to_parquet(path)
    return path
