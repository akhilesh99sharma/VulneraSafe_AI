"""Shared chronological (time-aware) train/test split helper (Phase 2).

This module defines the ONE canonical way the modeling layer splits a
``(state, period)`` modeling table into a training set and an untouched test
set. It is deliberately isolated here so that the baseline models (Task 3.4),
the integrated models (Task 3.5), and the time-aware validation (Task 3.7) all
reuse the exact same split and therefore report metrics on the exact same
untouched test period.

The split is STRICTLY CHRONOLOGICAL (Req 8.1 / design "Validation"):

* periods are ordered by their calendar ``period_start``;
* the most recent ``test_fraction`` (~20% by default) of the DISTINCT periods
  are reserved as the test set and are never seen during training or tuning;
* every training-row ``period_start`` is strictly earlier than every
  test-row ``period_start`` — there is no random shuffling and no period
  straddles the boundary.

The boundary is chosen on the set of *distinct* periods (not rows), so that all
rows of a given period land wholly on one side. The cut index is
``floor(n_periods * (1 - test_fraction))`` with guards that guarantee at least
one period on each side whenever there are >= 2 distinct periods.

Design reference: design.md "Validation (Req 8)" — chronological validation is
primary; the final ~20% of periods are held untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

__all__ = [
    "DEFAULT_TEST_FRACTION",
    "ChronoSplit",
    "distinct_periods_sorted",
    "chronological_split",
]

#: Default fraction of the most-recent distinct periods reserved, untouched, as
#: the test set (~20% per the design's "final 20% untouched" rule).
DEFAULT_TEST_FRACTION: float = 0.20


@dataclass(frozen=True)
class ChronoSplit:
    """A chronological split result.

    Attributes
    ----------
    train, test:
        The row-subset frames (views copied out of the source), already sorted
        by ``period_start`` then ``period``.
    boundary:
        The first ``period_start`` that belongs to the test set. Every training
        row has ``period_start < boundary`` and every test row has
        ``period_start >= boundary``.
    train_periods, test_periods:
        The sorted distinct period labels on each side.
    """

    train: pd.DataFrame
    test: pd.DataFrame
    boundary: pd.Timestamp
    train_periods: list[str]
    test_periods: list[str]

    @property
    def train_period_range(self) -> tuple[Optional[str], Optional[str]]:
        if not self.train_periods:
            return (None, None)
        return (self.train_periods[0], self.train_periods[-1])

    @property
    def test_period_range(self) -> tuple[Optional[str], Optional[str]]:
        if not self.test_periods:
            return (None, None)
        return (self.test_periods[0], self.test_periods[-1])


def distinct_periods_sorted(
    frame: pd.DataFrame,
    *,
    period_col: str = "period",
    start_col: str = "period_start",
) -> list[str]:
    """Return the distinct period labels ordered by their calendar start."""
    if frame.empty:
        return []
    starts = pd.to_datetime(frame[start_col])
    pairs = (
        pd.DataFrame({"period": frame[period_col].to_numpy(), "start": starts.to_numpy()})
        .drop_duplicates("period")
        .sort_values("start")
    )
    return pairs["period"].tolist()


def chronological_split(
    frame: pd.DataFrame,
    *,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    period_col: str = "period",
    start_col: str = "period_start",
) -> ChronoSplit:
    """Split ``frame`` chronologically into train / untouched test (Req 8.1).

    The most-recent ``test_fraction`` of the *distinct* periods form the test
    set; all earlier periods form the train set. The guarantee is that every
    train ``period_start`` is strictly less than every test ``period_start``.

    Parameters
    ----------
    frame:
        A modeling table carrying ``period_col`` and a datetime ``start_col``.
    test_fraction:
        Fraction (0 < f < 1) of the latest distinct periods to reserve as the
        untouched test set. Defaults to ~20%.

    Raises
    ------
    ValueError:
        If ``frame`` has fewer than two distinct periods (a chronological
        hold-out is undefined) or ``test_fraction`` is out of range.
    """
    if not (0.0 < test_fraction < 1.0):
        raise ValueError(f"test_fraction must be in (0, 1); got {test_fraction!r}")

    periods = distinct_periods_sorted(frame, period_col=period_col, start_col=start_col)
    n = len(periods)
    if n < 2:
        raise ValueError(
            f"need >= 2 distinct periods for a chronological split; got {n}"
        )

    # Number of periods reserved for test: at least 1, at most n-1 (keep >=1
    # period for training). Round to the nearest so ~20% lands close to 20%.
    n_test = int(round(n * test_fraction))
    n_test = max(1, min(n_test, n - 1))
    cut = n - n_test  # first `cut` periods are train, remainder are test

    train_periods = periods[:cut]
    test_periods = periods[cut:]
    train_set = set(train_periods)
    test_set = set(test_periods)

    starts = pd.to_datetime(frame[start_col])
    boundary = starts[frame[period_col].isin(test_set)].min()

    is_test = frame[period_col].isin(test_set)
    train = frame.loc[~is_test].copy()
    test = frame.loc[is_test].copy()

    # Deterministic ordering for reproducibility.
    for part in (train, test):
        part.sort_values([start_col, period_col], kind="mergesort", inplace=True)
        part.reset_index(drop=True, inplace=True)

    # Invariant guard (fails loudly rather than silently leaking): max train
    # start must be strictly less than min test start.
    if not train.empty and not test.empty:
        max_train = pd.to_datetime(train[start_col]).max()
        min_test = pd.to_datetime(test[start_col]).min()
        if not (max_train < min_test):
            raise AssertionError(
                "chronological_split produced overlapping periods: "
                f"max(train.period_start)={max_train} !< min(test.period_start)={min_test}"
            )

    assert not (train_set & test_set), "train/test period sets overlap"

    return ChronoSplit(
        train=train,
        test=test,
        boundary=pd.Timestamp(boundary),
        train_periods=train_periods,
        test_periods=test_periods,
    )
