"""Broker history: fetch, cache, and refuse to hand over data that is not true.

Two rules here earn their keep:

**Same source for research and execution.** Bars come from the same terminal that
would place the orders. Backtesting on someone else's gold prices and trading on
Exness's is validating a strategy that does not exist.

**Structural validity is not the same as being true.** The previous project's cache
passed every structural check — no gaps, no duplicates, no impossible OHLC — and
15% of its bars still recorded a spread of zero, which would have made those trades
free and manufactured an edge out of a data artefact. So the quality gate checks
the *plausibility* of the spread column too, not just its presence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import MetaTrader5 as mt5

TIMEFRAMES = {
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

BARS_PER_YEAR = {"M15": 96 * 260.0, "H1": 24 * 260.0, "H4": 6 * 260.0, "D1": 260.0}

# The terminal rejects an oversized range outright with `None (Invalid params)`
# rather than truncating it, so the REQUEST has to be chunked by time up front —
# reacting to a short response never happens, because there is no response.
_TARGET_BARS_PER_CALL = 30_000

_BARS_PER_DAY = {"M15": 96.0, "H1": 24.0, "H4": 6.0, "D1": 1.0}


@dataclass
class QualityReport:
    symbol: str
    timeframe: str
    n_bars: int
    first: pd.Timestamp
    last: pd.Timestamp
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coverage_by_year: dict[int, float] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return not self.failures

    def report(self) -> str:
        lines = [
            f"DATA QUALITY — {self.symbol} {self.timeframe}",
            "=" * 78,
            f"  bars     {self.n_bars:,}",
            f"  span     {self.first:%Y-%m-%d} .. {self.last:%Y-%m-%d}",
        ]
        if self.coverage_by_year:
            lines.append("  coverage by year (share of expected bars present):")
            for year, pct in sorted(self.coverage_by_year.items()):
                flag = "   <-- too thin to use" if pct < 50.0 else ""
                lines.append(f"    {year}  {pct:6.1f}%{flag}")
        for f in self.failures:
            lines.append(f"  [FAIL] {f}")
        for w in self.warnings:
            lines.append(f"  [WARN] {w}")
        if self.usable and not self.warnings:
            lines.append("  [OK] no issues found")
        lines.append(f"  VERDICT: {'USABLE' if self.usable else 'NOT USABLE'}")
        return "\n".join(lines)


def fetch(symbol: str, timeframe: str, start: datetime, end: datetime | None = None) -> pd.DataFrame:
    """Pull bars in chunks and return a tz-aware, deduplicated, sorted frame."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unknown timeframe {timeframe!r}; expected one of {list(TIMEFRAMES)}")
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"{symbol}: could not be selected in Market Watch")

    end = end or datetime.now(timezone.utc)
    tf = TIMEFRAMES[timeframe]

    chunk_days = max(1, int(_TARGET_BARS_PER_CALL / _BARS_PER_DAY[timeframe]))
    step = pd.Timedelta(days=chunk_days)

    frames, cursor, empty_chunks = [], pd.Timestamp(start), 0
    end_ts = pd.Timestamp(end)
    while cursor < end_ts:
        stop = min(cursor + step, end_ts)
        rates = mt5.copy_rates_range(symbol, tf, cursor.to_pydatetime(), stop.to_pydatetime())
        if rates is None or len(rates) == 0:
            # A genuinely empty window (before the archive starts, or a holiday
            # stretch) is normal. Only a total absence of data is an error.
            empty_chunks += 1
        else:
            frames.append(pd.DataFrame(rates))
        cursor = stop

    if not frames:
        code, desc = mt5.last_error()
        raise RuntimeError(
            f"{symbol} {timeframe}: no data in any of {empty_chunks} chunks ({code}: {desc})"
        )

    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.drop_duplicates(subset="time").sort_values("time").set_index("time")
    return df


def quality_gate(df: pd.DataFrame, symbol: str, timeframe: str) -> QualityReport:
    """Fail on data that is structurally broken; warn on data that is suspicious."""
    rep = QualityReport(
        symbol=symbol, timeframe=timeframe, n_bars=len(df),
        first=df.index[0], last=df.index[-1],
    )

    # --- structural failures: this data cannot be used at all ---
    if df.index.has_duplicates:
        rep.failures.append(f"{int(df.index.duplicated().sum())} duplicate timestamps")
    if not df.index.is_monotonic_increasing:
        rep.failures.append("timestamps are not sorted ascending")

    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            rep.failures.append(f"missing column '{col}'")
            continue
        if (df[col] <= 0).any():
            rep.failures.append(f"{int((df[col] <= 0).sum())} non-positive values in '{col}'")
        if df[col].isna().any():
            rep.failures.append(f"{int(df[col].isna().sum())} NaN values in '{col}'")

    if {"open", "high", "low", "close"}.issubset(df.columns):
        impossible = (
            (df["high"] < df["low"])
            | (df["high"] < df["open"]) | (df["high"] < df["close"])
            | (df["low"] > df["open"]) | (df["low"] > df["close"])
        )
        if impossible.any():
            rep.failures.append(f"{int(impossible.sum())} bars with impossible OHLC ordering")

    # --- spread plausibility: the check the previous project learned the hard way ---
    if "spread" in df.columns:
        spread = df["spread"]
        zeros = int((spread == 0).sum())
        if zeros:
            pct = zeros / len(df) * 100.0
            rep.warnings.append(
                f"{zeros:,} bars ({pct:.2f}%) record a spread of ZERO. A zero spread is not "
                "a price — it makes those trades free and can manufacture an edge. These "
                "must be floored before any cost model uses them."
            )
        distinct = int(spread.nunique())
        if distinct <= 10:
            top = spread.value_counts().head(5)
            share = top.sum() / len(df) * 100.0
            rep.warnings.append(
                f"only {distinct} distinct spread values; the top 5 cover {share:.1f}% of bars. "
                "This is the signature of a NOMINAL value backfilled by the server, not a "
                "recorded one. Treat spread as an assumption, not a measurement."
            )

    # --- coverage: a thin year wearing a full year's label ---
    expected_per_year = BARS_PER_YEAR.get(timeframe)
    if expected_per_year:
        for year, grp in df.groupby(df.index.year):
            pct = min(100.0, len(grp) / expected_per_year * 100.0)
            rep.coverage_by_year[int(year)] = pct

        thin = [y for y, p in rep.coverage_by_year.items() if p < 50.0]
        if thin:
            rep.warnings.append(
                f"years {thin} hold under half the bars an actual {timeframe} series contains. "
                "Backtesting across that boundary blends two different data resolutions and "
                "produces a number that means nothing. Use the continuous window instead."
            )

    return rep


def usable_window(rep: QualityReport, min_coverage_pct: float = 50.0) -> tuple[int, int] | None:
    """The longest run of consecutive years meeting the coverage bar.

    Returned separately from the headline span so that a deep-but-thin archive
    cannot quietly inflate how much history we claim to have.
    """
    years = sorted(y for y, p in rep.coverage_by_year.items() if p >= min_coverage_pct)
    if not years:
        return None
    best = run = [years[0]]
    for y in years[1:]:
        if y == run[-1] + 1:
            run.append(y)
        else:
            run = [y]
        if len(run) > len(best):
            best = list(run)
    return best[0], best[-1]


def cache_path(root: Path, symbol: str, timeframe: str) -> Path:
    return Path(root) / f"{symbol}_{timeframe}.parquet"


def save(df: pd.DataFrame, root: Path, symbol: str, timeframe: str) -> Path:
    path = cache_path(root, symbol, timeframe)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return path


def load(root: Path, symbol: str, timeframe: str) -> pd.DataFrame:
    path = cache_path(root, symbol, timeframe)
    if not path.exists():
        raise FileNotFoundError(f"no cached bars at {path}; run scripts/p1_fetch_history.py first")
    return pd.read_parquet(path)
