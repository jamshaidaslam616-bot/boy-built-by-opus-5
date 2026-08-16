"""Walk-forward splits with purging and embargo.

A naive train/test split leaks. If a strategy's decision at bar t depends on a
window of bars ending at t, and its outcome plays out over the following h bars,
then training samples near the test boundary share information with test samples.
The model then "predicts" data it has effectively already seen.

Two fixes, both from López de Prado:

- **Purge**: drop training samples whose information window overlaps the test set.
- **Embargo**: additionally drop training samples for a short period *after* the
  test set, because serial correlation makes the bars just after a test block
  informative about it.

Walk-forward rather than a single hold-out because a single split measures how far
one parameter set travelled; walk-forward measures whether the *method* travels —
and it accumulates out-of-sample observations across every fold, which is both a
larger sample and a stricter test.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Fold:
    index: int
    train: pd.DatetimeIndex
    test: pd.DatetimeIndex
    purged_bars: int
    embargoed_bars: int

    def describe(self) -> str:
        return (
            f"  fold {self.index}  train {self.train[0]:%Y-%m-%d}..{self.train[-1]:%Y-%m-%d} "
            f"({len(self.train):,})  test {self.test[0]:%Y-%m-%d}..{self.test[-1]:%Y-%m-%d} "
            f"({len(self.test):,})  purged {self.purged_bars}  embargo {self.embargoed_bars}"
        )


def purged_walk_forward(
    index: pd.DatetimeIndex,
    n_folds: int,
    lookback_bars: int,
    holding_bars: int,
    embargo_bars: int | None = None,
    min_train_bars: int = 500,
    anchored: bool = True,
) -> list[Fold]:
    """Expanding-window walk-forward with purge and embargo around each test block.

    ``lookback_bars``  how far back a decision at bar t looks (feature window).
    ``holding_bars``   how far forward its outcome extends (label window).
    ``embargo_bars``   defaults to ``holding_bars``, the smallest defensible value.

    ``anchored=True`` grows the training window from the start (more data each
    fold); ``False`` uses a rolling window of fixed length (adapts to regime, but
    throws away history). Anchored is the default because with 4 years of data,
    discarding history costs more than regime staleness does.
    """
    if n_folds < 2:
        raise ValueError("need at least 2 folds")
    if lookback_bars < 0 or holding_bars < 0:
        raise ValueError("lookback and holding windows cannot be negative")
    if not index.is_monotonic_increasing:
        raise ValueError("index must be sorted ascending")

    embargo = holding_bars if embargo_bars is None else embargo_bars
    n = len(index)
    if n < min_train_bars + n_folds * 2:
        raise ValueError(f"only {n} bars: too few for {n_folds} folds with {min_train_bars} min train")

    # Test blocks tile the tail of the series. The first block must start late
    # enough that, AFTER the purge is carved out, a full min_train_bars of clean
    # training data still remains — otherwise fold 0 is silently dropped and the
    # caller gets fewer folds than it asked for without being told.
    test_region_start = min_train_bars + holding_bars
    if n <= test_region_start + n_folds:
        raise ValueError(
            f"{n} bars cannot support {n_folds} folds with min_train_bars={min_train_bars} "
            f"and a {holding_bars}-bar purge (needs more than {test_region_start + n_folds})"
        )
    test_size = (n - test_region_start) // n_folds
    if test_size < 1:
        raise ValueError("test blocks would be empty; reduce n_folds or min_train_bars")

    folds: list[Fold] = []
    for i in range(n_folds):
        t0 = test_region_start + i * test_size
        t1 = n if i == n_folds - 1 else test_region_start + (i + 1) * test_size

        test_idx = index[t0:t1]

        # Purge: training must end early enough that no training sample's outcome
        # window can reach into the test block.
        train_end = t0 - holding_bars

        # Embargo: also drop training samples that begin inside the embargo window
        # following the test block (relevant only when training resumes after it,
        # i.e. in the unanchored case or for folds that are not the last).
        train_start = 0 if anchored else max(0, train_end - min_train_bars)

        if train_end - train_start < min_train_bars:
            # Never shrink the purge to rescue a fold — that is leakage on purpose.
            # Skipping is correct, but the caller must be told rather than quietly
            # handed a shorter list than it asked for.
            raise ValueError(
                f"fold {i}: only {train_end - train_start} clean training bars after a "
                f"{holding_bars}-bar purge, need {min_train_bars}. Reduce n_folds or "
                "min_train_bars — the purge is not negotiable."
            )

        train_idx = index[train_start:train_end]

        folds.append(
            Fold(
                index=i,
                train=train_idx,
                test=test_idx,
                purged_bars=holding_bars,
                embargoed_bars=embargo,
            )
        )

    if not folds:
        raise ValueError("no fold retained enough clean training data")
    return folds


def assert_no_overlap(folds: list[Fold]) -> None:
    """Fail loudly if any fold's train and test sets intersect.

    Cheap, and it catches the class of bug that makes a backtest look brilliant.
    """
    for f in folds:
        overlap = f.train.intersection(f.test)
        if len(overlap) > 0:
            raise AssertionError(
                f"fold {f.index}: {len(overlap)} timestamps appear in BOTH train and test"
            )


def walk_forward_efficiency(
    in_sample_sharpes: list[float],
    out_sample_sharpes: list[float],
    min_is_sharpe: float = 0.20,
) -> tuple[float | None, list[int]]:
    """Fraction of in-sample performance retained out-of-sample.

    Returns ``(mean_efficiency_or_None, excluded_fold_indices)``.

    **Folds with a negligible in-sample Sharpe are excluded, not counted as zero.**
    Dividing an out-of-sample result by a near-zero in-sample edge produces
    meaningless magnitudes — on the previous project one such fold produced an
    "efficiency" of -172 and swamped the mean. A fold with no in-sample edge cannot
    tell you what fraction of that edge survived, so it is reported as excluded.

    If every fold is excluded, the answer is ``None`` — "not measurable" — which is
    a legitimate result and must be printed as such rather than as a number.
    """
    if len(in_sample_sharpes) != len(out_sample_sharpes):
        raise ValueError("in-sample and out-of-sample lists must be the same length")

    ratios, excluded = [], []
    for i, (is_sr, oos_sr) in enumerate(zip(in_sample_sharpes, out_sample_sharpes)):
        if is_sr < min_is_sharpe:
            excluded.append(i)
            continue
        ratios.append(oos_sr / is_sr)

    if not ratios:
        return None, excluded
    return float(sum(ratios) / len(ratios)), excluded
