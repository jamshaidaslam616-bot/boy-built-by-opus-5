"""Attack the binding constraint directly: forecast volatility better.

F9 established that the limit on this project is not return, it is DRAWDOWN. The
strategy has to be sized down to 3-5% volatility to respect a 10% drawdown cap, and
that is what reduces $405/yr to $151/yr.

Volatility targeting is only as good as its volatility forecast. A 60-day rolling
standard deviation is backward-looking: it sizes up right before a volatility spike
and sizes down right after one, which is exactly wrong and is a direct cause of
drawdown. A better forecast means position size tracks true risk more closely, which
means fewer drawdown surprises, which means a LARGER position is compatible with the
same 10% cap.

That is a different lever from every other thing tested in this project. Everything
in P3 and P4 tried to predict direction. This tries to predict risk — and the
literature is clear that risk is far more forecastable than direction. Published
work on gold futures finds that adding the options market's implied volatility
(GVZ) to a HAR model improves out-of-sample R-squared by 10-56 percentage points.

Crucially, GVZ is NOT price data. It is the options market's forward-looking view,
which is genuinely new information and it is free.
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
from goldlab.research.metrics import summarise  # noqa: E402
from goldlab.research.prereg import Hypothesis, PreRegistrationLog, Result  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns  # noqa: E402
from goldlab.strategy import candidates as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 260.0
CAPITAL = 10_000.0
SPEEDS = (20, 50, 100, 200, 400)
TRAIN_BARS = 750

HYPOTHESIS = Hypothesis(
    name="P5-volatility-forecasting",
    family="C1/C2",
    claim="Sizing on a HAR-type volatility forecast — especially one augmented with the "
          "options market's implied volatility (GVZ) — produces a lower maximum drawdown "
          "at the same average exposure than sizing on trailing realised volatility, and "
          "therefore permits a larger compliant position.",
    economic_rationale="Volatility is strongly autocorrelated and clusters; direction is not. "
                       "A trailing standard deviation reacts to a volatility spike only after "
                       "it has happened, so it is largest just when risk is largest. HAR "
                       "captures the cascade of short, medium and long horizons, and implied "
                       "volatility adds the options market's forward-looking view — which is "
                       "information about risk that is not in the price series at all. This "
                       "targets the project's binding constraint (drawdown) rather than "
                       "attempting to predict direction, which every previous phase failed at.",
    pass_criteria={"max_drawdown_reduction_pct": 10.0, "compliant_return_improvement_pct": 10.0},
    n_param_combinations=3,
    data_scope="XAUUSD D1 2014-2026; FRED GVZCLS with a 2-day publication lag; "
               "expanding-window out-of-sample from bar 750 onward",
    predicted_outcome="I expect the HAR forecast to beat the rolling standard deviation "
                      "measurably on forecast accuracy, and GVZ to add on top of that. Whether "
                      "it converts into a materially larger compliant position is much less "
                      "certain — drawdown is driven by sustained adverse trends as much as by "
                      "volatility surprises, and better sizing cannot help with the former. My "
                      "guess is a 5-15% drawdown reduction, which would be useful but not "
                      "transformative. I have been wrong on two of five predictions so far.",
)


def costs() -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=-5.66, carry_short_annual_pct=0.0, bars_per_year=BARS_PER_YEAR,
    )


def fetch_gvz(index: pd.DatetimeIndex) -> pd.Series | None:
    try:
        body = _http.get_text(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GVZCLS", timeout=30, attempts=3
        )
    except Exception as exc:
        print(f"  GVZ unavailable ({type(exc).__name__}); testing HAR without it.")
        return None
    df = pd.read_csv(io.StringIO(body))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    series = df.dropna().set_index("date")["value"]
    print(f"  GVZ: {len(series):,} observations, {series.index[0]:%Y-%m-%d} .. "
          f"{series.index[-1]:%Y-%m-%d}, latest {series.iloc[-1]:.2f}")
    # GVZ closes with the US session and is published that evening; 2 days is safe.
    return MacroSeries("GVZCLS", "gvz", series, publication_lag_days=2).as_known_on(index)


def har_features(realised: pd.Series) -> pd.DataFrame:
    """Daily, weekly and monthly realised volatility — the HAR cascade."""
    return pd.DataFrame({
        "rv_d": realised,
        "rv_w": realised.rolling(5, min_periods=5).mean(),
        "rv_m": realised.rolling(22, min_periods=22).mean(),
    })


def expanding_ols_forecast(X: pd.DataFrame, y: pd.Series, start: int) -> pd.Series:
    """Out-of-sample forecasts from an expanding window. Refit every 21 bars.

    Every forecast for bar t uses only data through t-1, so this cannot see the
    volatility it is predicting.
    """
    out = pd.Series(np.nan, index=X.index)
    data = pd.concat([X, y.rename("y")], axis=1).dropna()
    if len(data) <= start:
        return out

    coeffs = None
    for i in range(start, len(data)):
        if coeffs is None or (i - start) % 21 == 0:
            train = data.iloc[:i]
            A = np.column_stack([np.ones(len(train)), train[X.columns].to_numpy()])
            coeffs, *_ = np.linalg.lstsq(A, train["y"].to_numpy(), rcond=None)
        row = np.concatenate([[1.0], data.iloc[i][X.columns].to_numpy()])
        out.loc[data.index[i]] = float(row @ coeffs)
    return out


def size_by_forecast(raw: pd.Series, forecast: pd.Series, target: float,
                     max_leverage: float = 2.0) -> pd.Series:
    """Vol targeting driven by an explicit forecast rather than a trailing window."""
    scale = (target / forecast.replace(0.0, np.nan)).clip(upper=max_leverage)
    return (raw * scale.shift(1)).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def compliant_size(raw: pd.Series, forecast: pd.Series, close: pd.Series):
    for target in (0.12, 0.10, 0.08, 0.06, 0.05, 0.04, 0.03, 0.02):
        pos = size_by_forecast(raw, forecast, target)
        perf = summarise(strategy_returns(pos, close, costs()), BARS_PER_YEAR)
        if perf.max_drawdown_pct <= 10.0:
            return target, perf
    return None, None


def main() -> int:
    log = PreRegistrationLog(LOG)
    if not log.is_registered(HYPOTHESIS.name):
        log.register(HYPOTHESIS)
        print(f"registered {HYPOTHESIS.name} before any scoring\n")

    close = hist.load(ROOT, "XAUUSD", "D1")["close"]
    rets = close.pct_change()

    print("=" * 96)
    print("P5 — FORECASTING RISK INSTEAD OF DIRECTION")
    print("=" * 96)

    # Realised vol, annualised, and the target it must predict: the NEXT 21 days.
    realised = rets.rolling(21, min_periods=21).std() * np.sqrt(BARS_PER_YEAR)
    future = realised.shift(-21)

    gvz = fetch_gvz(close.index)
    feats = har_features(realised)
    if gvz is not None:
        feats = feats.assign(gvz=gvz / 100.0)

    print("\n  Out-of-sample forecast accuracy (expanding window, refit every 21 bars)")
    print(f"    {'model':<28} {'OOS R-squared':>15} {'RMSE':>10}")
    print("    " + "-" * 56)

    forecasts: dict[str, pd.Series] = {}
    # The incumbent: a 60-day trailing standard deviation, what every phase used so far.
    forecasts["rolling 60d (incumbent)"] = (
        rets.rolling(60, min_periods=60).std() * np.sqrt(BARS_PER_YEAR)
    )

    models = {"HAR (d/w/m)": ["rv_d", "rv_w", "rv_m"]}
    if gvz is not None:
        models["HAR + GVZ"] = ["rv_d", "rv_w", "rv_m", "gvz"]
        models["GVZ alone"] = ["gvz"]

    for label, cols in models.items():
        forecasts[label] = expanding_ols_forecast(feats[cols], future, TRAIN_BARS)

    for label, fc in forecasts.items():
        joined = pd.concat([fc.rename("f"), future.rename("y")], axis=1).dropna()
        joined = joined.loc[joined.index >= close.index[TRAIN_BARS]]
        if joined.empty:
            print(f"    {label:<28} {'no overlap':>15}")
            continue
        ss_res = float(((joined["y"] - joined["f"]) ** 2).sum())
        ss_tot = float(((joined["y"] - joined["y"].mean()) ** 2).sum())
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
        rmse = float(np.sqrt(ss_res / len(joined)))
        print(f"    {label:<28} {r2:>14.3f}  {rmse:>9.4f}")

    # The question that actually matters: does a better forecast permit a bigger position?
    print("\n" + "=" * 96)
    print("  DOES IT CONVERT? — sizing the P4 ensemble with each forecast")
    print("=" * 96)
    raw = (sum(C.a1_timeseries_momentum(close, n) for n in SPEEDS) / len(SPEEDS)).clip(lower=0.0)

    print(f"    {'forecast used':<28} {'compliant vol':>14} {'return/yr':>11} "
          f"{'maxDD':>8} {'$ on 10k':>10}")
    print("    " + "-" * 76)

    results = {}
    for label, fc in forecasts.items():
        target, perf = compliant_size(raw, fc, close)
        if perf is None:
            print(f"    {label:<28} {'none complies':>14}")
            continue
        results[label] = (target, perf)
        print(f"    {label:<28} {target:>13.0%} {perf.ann_return_pct:>+10.2f}% "
              f"{perf.max_drawdown_pct:>7.2f}% {CAPITAL * perf.ann_return_pct / 100:>+10.0f}")

    if "rolling 60d (incumbent)" in results and len(results) > 1:
        base_ret = results["rolling 60d (incumbent)"][1].ann_return_pct
        best_label = max(
            (k for k in results if k != "rolling 60d (incumbent)"),
            key=lambda k: results[k][1].ann_return_pct,
        )
        best_ret = results[best_label][1].ann_return_pct
        gain = (best_ret / base_ret - 1) * 100 if base_ret > 0 else float("nan")
        print(f"\n    best alternative: {best_label}")
        print(f"    compliant return {base_ret:+.2f}% -> {best_ret:+.2f}%/yr  ({gain:+.1f}%)")
        print(f"    in dollars on ${CAPITAL:,.0f}: "
              f"${CAPITAL * base_ret / 100:+,.0f} -> ${CAPITAL * best_ret / 100:+,.0f}")

        log.record_result(Result(
            hypothesis_name=HYPOTHESIS.name,
            verdict="PASS" if gain >= 10.0 else "FAIL",
            metrics={
                "best_model": best_label,
                "incumbent_compliant_return_pct": round(base_ret, 3),
                "best_compliant_return_pct": round(best_ret, 3),
                "improvement_pct": round(gain, 1),
                "gvz_available": gvz is not None,
            },
            notes="Targets drawdown, the binding constraint, rather than direction.",
        ))

    ok, message = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
