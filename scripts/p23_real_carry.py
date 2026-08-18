"""Carry, measured from actual policy rates instead of the broker's fee schedule.

P22 tested "carry" using the broker's swap differentials and it failed. That result
does not count, and saying why matters more than the number did: the measured values
included +40% on UKOIL and +31% on USOIL, where genuine FX carry differentials run
0-5%. Those are a markup, not a rate. The test traded this broker's pricing and
learned nothing about the anomaly.

The FX carry trade — long the high-yielding currency, short the low-yielding one —
is the most documented effect in currencies, with evidence going back decades. It
requires the actual short-term interest rate of each country, which FRED publishes
for the OECD, and which has been available this whole time.

Only the currency pairs are testable here. Metals, energy, indices and crypto have
no policy rate, so they are excluded rather than assigned a fabricated one.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import _http  # noqa: E402
from goldlab.data import history as hist  # noqa: E402
from goldlab.data.macro import MacroSeries  # noqa: E402
from goldlab.research.control import circular_shift_controls  # noqa: E402
from goldlab.research.metrics import sharpe_ratio, summarise  # noqa: E402
from goldlab.research.prereg import Hypothesis, PreRegistrationLog, Result  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 260.0
REBAL = 5
VOL_LB = 60

# BIS central bank policy rates, one per currency. FRED and the ECB's own API both
# refuse this host, while BIS, CFTC and Yahoo answer normally — so the block is
# per-source, not a network fault, and BIS carries exactly the series needed.
#
# Policy rates rather than interbank rates. They are what a central bank sets, they
# are published monthly for every country here, and the differential between two of
# them IS the carry the literature trades. Interbank rates would be marginally
# closer to what a trader actually earns; policy rates are what is reachable, and
# the difference between the two is far smaller than the differentials being ranked.
BIS_URL = ("https://stats.bis.org/api/v1/data/BIS,WS_CBPOL,1.0/M.{area}"
           "?format=csv&startPeriod=2014-01")
RATES = {
    "USD": "US", "EUR": "XM", "JPY": "JP", "GBP": "GB", "CHF": "CH", "CAD": "CA",
    "AUD": "AU", "NZD": "NZ", "NOK": "NO", "SEK": "SE", "MXN": "MX", "PLN": "PL",
}

# base/quote per symbol. Carry of being LONG = base rate - quote rate.
PAIRS = {
    "EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"), "AUDUSD": ("AUD", "USD"),
    "NZDUSD": ("NZD", "USD"), "USDJPY": ("USD", "JPY"), "USDCHF": ("USD", "CHF"),
    "USDCAD": ("USD", "CAD"), "USDNOK": ("USD", "NOK"), "USDSEK": ("USD", "SEK"),
    "USDMXN": ("USD", "MXN"), "USDPLN": ("USD", "PLN"),
}

HYPOTHESIS = Hypothesis(
    name="P23-real-fx-carry",
    family="cross-sectional",
    claim="Ranking currency pairs by their genuine interest rate differential and holding the "
          "high-yielders against the low-yielders earns a positive return net of costs.",
    economic_rationale="The most documented anomaly in currencies. Uncovered interest parity "
                       "predicts that high-yielding currencies depreciate enough to offset "
                       "their yield; empirically they do not, and the gap has been the carry "
                       "trade for forty years. It is a genuinely different mechanism from "
                       "momentum — a compensation for bearing crash risk rather than a price "
                       "pattern — so it should correlate weakly with everything tested so far.",
    pass_criteria={"control_rotation_z": 2.0},
    n_param_combinations=2,
    data_scope="11 FX pairs with BIS central bank policy rates, D1, monthly rates lagged 45 days",
    predicted_outcome="Genuinely uncertain and the best remaining shot. The effect is real in "
                      "the literature but it has been weak since 2008 — central bank rates "
                      "converged to zero for a decade, which removes the differential the trade "
                      "depends on, and this window starts in 2020. Eleven pairs is also a thin "
                      "cross-section for a factor usually run on thirty. I would put it at "
                      "maybe a third to clear zero and well under that to clear the control. "
                      "Wrong on 5 of 14 predictions, mostly optimistic.",
)


def fetch_rate(currency: str, area: str) -> pd.Series | None:
    try:
        body = _http.get_text(BIS_URL.format(area=area), timeout=30, attempts=3)
    except Exception as exc:
        print(f"    {currency:<4} BIS/{area:<3} unavailable ({type(exc).__name__})")
        return None
    df = pd.read_csv(io.StringIO(body))
    if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
        print(f"    {currency:<4} BIS/{area:<3} unexpected columns: {list(df.columns)[:4]}")
        return None
    df = df[["TIME_PERIOD", "OBS_VALUE"]].dropna()
    df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"], utc=True)
    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
    s = df.dropna().set_index("TIME_PERIOD")["OBS_VALUE"].sort_index()
    if s.empty:
        print(f"    {currency:<4} BIS/{area:<3} no observations")
        return None
    print(f"    {currency:<4} BIS/{area:<3} {len(s):>4} obs, "
          f"{s.index[-1]:%Y-%m}, latest {s.iloc[-1]:+.2f}%")
    return s


def main() -> int:
    log = PreRegistrationLog(LOG)
    if not log.is_registered(HYPOTHESIS.name):
        log.register(HYPOTHESIS)
        print(f"registered {HYPOTHESIS.name} before any scoring\n")

    print("=" * 92)
    print("P23 — FX CARRY FROM ACTUAL POLICY RATES")
    print("=" * 92)
    print("\n  fetching 3-month interbank rates from FRED:")
    rates = {c: fetch_rate(c, sid) for c, sid in RATES.items()}
    rates = {c: s for c, s in rates.items() if s is not None}
    print(f"\n  {len(rates)}/{len(RATES)} currencies available")

    usable = [p for p, (b, q) in PAIRS.items() if b in rates and q in rates]
    if len(usable) < 6:
        print(f"  only {len(usable)} pairs have both legs; too few for a cross-section")
        return 1

    panel = pd.DataFrame({s: hist.load(ROOT, s, "D1")["close"] for s in usable})
    panel = panel.loc[panel.notna().all(axis=1)]
    vol = panel.pct_change().rolling(VOL_LB).std()

    # Monthly series published with a lag; 45 days is conservative and point-in-time.
    aligned = {
        c: MacroSeries(RATES[c], c, s, publication_lag_days=45).as_known_on(panel.index)
        for c, s in rates.items()
    }

    carry = pd.DataFrame({
        p: aligned[PAIRS[p][0]] - aligned[PAIRS[p][1]] for p in usable
    }, index=panel.index)

    print(f"\n  {len(usable)} pairs, {len(panel):,} bars, "
          f"{panel.index[0]:%Y-%m-%d} .. {panel.index[-1]:%Y-%m-%d}")
    print("\n  carry (annual % of being long), latest — these are RATE differentials:")
    latest = carry.iloc[-1].sort_values(ascending=False)
    for p, v in latest.items():
        print(f"    {p:<9} {v:+6.2f}%")

    legs = max(2, len(usable) // 3)
    print(f"\n  book: long the top {legs}, short the bottom {legs}, weekly rebalance")

    r = carry.rank(axis=1, ascending=False)
    raw = pd.DataFrame(0.0, index=carry.index, columns=carry.columns)
    raw[r <= legs] = 1.0
    raw[r > len(usable) - legs] = -1.0
    raw = raw.where(carry.notna(), 0.0)

    sized = (raw / vol.replace(0.0, np.nan))
    sized = sized.div(sized.abs().sum(axis=1), axis=0).fillna(0.0)
    grid = pd.Series(np.arange(len(sized)) % REBAL == 0, index=sized.index)
    pos = sized.where(grid, np.nan).ffill().fillna(0.0)

    costs = CostModel(spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
                      carry_long_annual_pct=0.0, carry_short_annual_pct=0.0,
                      bars_per_year=BARS_PER_YEAR)

    def book(p: pd.DataFrame) -> pd.Series:
        t = None
        for c in panel.columns:
            leg = strategy_returns(p[c], panel[c], costs)
            t = leg if t is None else t + leg
        return t

    rets = book(pos)
    perf = summarise(rets, BARS_PER_YEAR)
    rng = np.random.default_rng(20260817)
    ctrl = np.array([sharpe_ratio(book(pd.DataFrame(
        {c: circular_shift_controls(pos[c], 1, seed=int(rng.integers(1e9)))[0]
         for c in pos.columns}, index=pos.index)), BARS_PER_YEAR) for _ in range(80)])
    z = (perf.sharpe - ctrl.mean()) / ctrl.std(ddof=1)

    print("\n" + "=" * 92)
    print("  RESULT")
    print("=" * 92)
    print(f"    Sharpe {perf.sharpe:+.3f}   return {perf.ann_return_pct:+.2f}%/yr   "
          f"maxDD {perf.max_drawdown_pct:.2f}%")
    print(f"    control: strategy {perf.sharpe:+.3f} vs rotations {ctrl.mean():+.3f} "
          f"+/- {ctrl.std(ddof=1):.3f}")
    print(f"    z = {z:+.2f}   percentile {float((ctrl < perf.sharpe).mean() * 100):.1f}   "
          f"{'PASS' if z >= 2 else 'FAIL'}")
    if perf.sharpe > 0:
        print(f"    years to prove {(2.0 / perf.sharpe) ** 2:.1f} "
              f"(this window has {len(rets) / BARS_PER_YEAR:.1f})")

    log.record_result(Result(
        hypothesis_name=HYPOTHESIS.name,
        verdict="PASS" if z >= 2.0 else "FAIL",
        metrics={"sharpe": round(perf.sharpe, 4), "z": round(float(z), 3),
                 "pairs": len(usable), "legs_per_side": legs,
                 "return_pct": round(perf.ann_return_pct, 3)},
        notes="Rates from FRED 3-month interbank, lagged 45 days. Supersedes P22's carry test, "
              "which used broker swap differentials and therefore measured a fee schedule.",
    ))
    ok, msg = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
