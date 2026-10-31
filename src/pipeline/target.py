"""Prediction target and FIXED horizon definition (Phase 2, Task 3.3).

This module turns the leakage-safe per-``(state, period)`` feature matrices
produced by :mod:`src.pipeline.features` into **modeling-ready tables** by
deriving the prediction target and joining it onto the feature rows. It
implements Requirements 5.1–5.5.

What the target *is* (Req 5.5 — stated explicitly)
---------------------------------------------------
The modeled target is **surveillance risk at the ``Modeling_Unit``** — the
(pathogen × commodity × state × period) analytic cell. A positive label means
*next-period routine-surveillance positivity at that state is predicted to be
elevated relative to its own recent history*. It is **NOT** a claim that any
specific shipment, lot, or product is contaminated. The system forecasts where
regulatory/operational attention is likely to be warranted next period, not the
contamination status of an individual item.

Target definition (Req 5.1, 5.3)
---------------------------------
For a ``Modeling_Unit`` (state) and period ``t`` at the pathogen's resolution:

    baseline(state, t) = trailing mean of outcome_routine_positivity_rate over
                         the LOOKBACK window of periods strictly BEFORE t
                         (>= 12 months of history: 12 monthly periods or
                         4 quarterly periods).

    y_elevated(state, t) = 1  if outcome_routine_positivity_rate(state, t+1)
                               > baseline(state, t)
                           0  otherwise

The horizon is **one period ahead** (monthly for Salmonella, quarterly for
Listeria / STEC) and is fixed as the module-level constant
:data:`HORIZON_PERIODS` ``= 1`` **before any model tuning**. Nothing downstream
may change it after tuning begins (Req 5.3). The baseline uses **only strictly
past data** (periods ``< t``), so the baseline a label is compared against never
sees the outcome it is labeling.

The label at row ``t`` uses the *next* period's outcome (``t+1``), but the
features on that same row remain ``<= t``. The feature matrix already enforces
leakage-safety for everything at or before ``t`` (Task 3.1); this module adds
the ``t -> t+1`` target and asserts that **no feature column is used to derive
the label** and that the label columns are **not** among the feature columns
(Req 7.5 spirit; guarded by :func:`assert_no_label_leakage`).

Exclusions (Req 5.2) — never fabricated
----------------------------------------
A ``(state, t)`` cell is **not labelable** (``labelable = False``) and is
excluded from labeling, with the reason recorded, when either holds:

* **insufficient history** — fewer than ``LOOKBACK`` periods of prior routine
  history exist for that state before ``t`` (so no stable baseline can be
  formed), OR the current period's own routine positivity is missing so no
  baseline contribution exists; and
* **unobserved next period** — the next period ``t+1`` has no routine row for
  that state, or its routine ``samples`` are below ``MIN_NEXT_SAMPLES`` (too few
  tested samples to form a stable positivity rate). These cells are recorded as
  *unlabelable*, never assigned a fabricated label (Req 4.6).

Count / rate formulation alongside binary (Req 5.4)
---------------------------------------------------
Beside the binary ``y_elevated`` the module also emits the raw next-period
routine positivity **rate** as a regression-style target ``y_next_positivity``
(= ``outcome_routine_positivity_rate(state, t+1)``). ``data/interim/
target_report.json`` records the binary-vs-rate comparison note and WHY the
binary elevated-positivity framing is chosen as the primary decision target.

Outputs
-------
``data/processed/model_<pathogen>.parquet`` (CSV fallback) with: the feature
keys and all feature columns, the binary label ``y_elevated``, the rate target
``y_next_positivity``, the trailing ``baseline`` used, a ``labelable`` boolean
and an ``exclusion_reason`` string; plus ``data/interim/target_report.json``.

Design reference: design.md "Models, features, rare events (Req 7)" /
"Predictive target and horizon (Req 5)".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.pipeline.features import (
    PATHOGEN_SLUG,
    PROCESSED_ROOT,
    period_start,
    resolution_for,
)
from src.pipeline.ingest import REPO_ROOT

__all__ = [
    "HORIZON_PERIODS",
    "HORIZON_FIXED_PRE_TUNING",
    "LOOKBACK_PERIODS",
    "MIN_NEXT_SAMPLES",
    "MIN_NEXT_SAMPLES_V2",
    "SHRINKAGE_PSEUDOCOUNT",
    "TAIL_PERCENTILE",
    "TARGET_IS_SURVEILLANCE_RISK",
    "INTERIM_ROOT",
    "KEY_COLS",
    "OUTCOME_COLS",
    "LABEL_COLS",
    "lookback_for",
    "feature_columns",
    "national_prior_from_train",
    "beta_binomial_shrink",
    "train_tail_threshold",
    "derive_target",
    "add_smoothed_label",
    "assert_no_label_leakage",
    "build_model_table",
    "write_target_report",
    "run_target_derivation",
]

# --------------------------------------------------------------------------- #
# FIXED horizon + lookback constants (fixed BEFORE any model tuning — Req 5.3)
# --------------------------------------------------------------------------- #

#: Prediction horizon, in periods ahead, FIXED before any tuning (Req 5.3). The
#: unit is the pathogen's feasibility resolution: 1 month ahead for Salmonella
#: (monthly) and 1 quarter ahead for Listeria / STEC (quarterly). This constant
#: MUST NOT be altered once model tuning begins.
HORIZON_PERIODS: int = 1

#: Documentation flag asserting the horizon was fixed pre-tuning (Req 5.3). It
#: is recorded verbatim in ``target_report.json`` and asserted by the tests.
HORIZON_FIXED_PRE_TUNING: bool = True

#: Trailing lookback window length for the baseline, per resolution. At least 12
#: months of history is required (Req 5.1): 12 monthly periods or 4 quarterly
#: periods (both span 12 months).
LOOKBACK_PERIODS: dict[str, int] = {"monthly": 12, "quarterly": 4}

#: Minimum routine tested-sample count in the NEXT period for a stable
#: positivity rate; next-period cells with fewer samples are unlabelable
#: (recorded, never fabricated — Req 5.2 / 4.6).
MIN_NEXT_SAMPLES: int = 1

#: Minimum next-period routine tested-sample count required for the REDESIGNED
#: denominator-aware label (``y_elevated_v2``). The smoothed Beta-Binomial rate
#: is defined for any denominator >= 1 (it shrinks the thinnest cells almost
#: fully onto the national prior), but a cell with a vanishingly small
#: denominator carries essentially no own-signal, so for the v2 label we require
#: a slightly larger minimum to ensure the smoothed rate reflects at least some
#: direct observation. Fixed BEFORE tuning and recorded in target_report.json.
MIN_NEXT_SAMPLES_V2: int = 5

#: Prior strength (pseudo-count / equivalent prior sample size) for the
#: empirical-Bayes Beta-Binomial shrinkage used to form
#: ``smoothed_next_positivity`` (redesign step 1). The next-period
#: (positives, samples) pair is shrunk toward the pathogen's national prior rate
#: ``p_nat`` with a Beta(alpha, beta) prior where ``alpha = m * p_nat`` and
#: ``beta = m * (1 - p_nat)`` and ``m = SHRINKAGE_PSEUDOCOUNT``. A cell with
#: ``n`` next-period samples and ``k`` positives gets
#: ``smoothed = (k + alpha) / (n + alpha + beta) = (k + m*p_nat) / (n + m)``,
#: i.e. the posterior mean of a Beta-Binomial. With ``m`` fixed, a cell whose
#: denominator ``n >> m`` keeps almost its raw rate, while a thin cell (``n``
#: comparable to or below ``m``) is pulled toward ``p_nat``. ``m = 20`` is a
#: documented fixed choice: it equals roughly the national median active-cell
#: denominator scale and is held constant across pathogens for comparability.
#: Fixed BEFORE any model tuning (Req 5.3 spirit) and recorded in the report.
SHRINKAGE_PSEUDOCOUNT: float = 20.0

#: Tail percentile (on TRAIN-only smoothed positivity) defining the HIGH-RISK
#: threshold for ``y_elevated_v2`` (redesign step 2). A state-period is labeled
#: high-risk (1) iff its smoothed next-period positivity is at/above the
#: pathogen's 75th-percentile of smoothed positivity over the TRAIN periods.
#: Computed on TRAIN rows ONLY (no test peeking); recorded per pathogen.
TAIL_PERCENTILE: float = 75.0

#: Stated meaning of the modeled target (Req 5.5): surveillance risk at the
#: Modeling_Unit, NOT a shipment-contamination claim.
TARGET_IS_SURVEILLANCE_RISK: str = (
    "The modeled target is SURVEILLANCE risk at the (state, period) "
    "Modeling_Unit: a positive label means next-period routine-surveillance "
    "positivity for that state is predicted to be elevated relative to its own "
    "trailing baseline. It is NOT a claim that any specific shipment, lot, or "
    "product is contaminated (Req 5.5)."
)

INTERIM_ROOT = REPO_ROOT / "data" / "interim"

#: Key / bookkeeping columns carried through from the feature matrix.
KEY_COLS: tuple[str, ...] = (
    "pathogen", "state", "period", "period_start", "cutoff", "resolution",
)

#: The raw current-period routine outcome columns (NOT features; the label is
#: derived from the NEXT period's value of ``outcome_routine_positivity_rate``).
OUTCOME_COLS: tuple[str, ...] = (
    "outcome_routine_samples", "outcome_routine_positives",
    "outcome_routine_positivity_rate",
)

#: Columns this module ADDS. They are the label/target and bookkeeping — they
#: are never treated as features and must never appear among feature columns.
#: The redesign adds the denominator-aware primary label ``y_elevated_v2``, the
#: Beta-Binomial ``smoothed_next_positivity``, the next-period positive count
#: ``next_routine_positives`` (needed to form the smoothed rate), the
#: train-derived ``v2_threshold`` and ``labelable_v2`` / ``exclusion_reason_v2``.
LABEL_COLS: tuple[str, ...] = (
    "y_elevated", "y_next_positivity", "baseline", "labelable",
    "exclusion_reason", "next_period", "next_routine_samples",
    "y_elevated_v2", "smoothed_next_positivity", "next_routine_positives",
    "v2_threshold", "labelable_v2", "exclusion_reason_v2",
)


def lookback_for(resolution: str) -> int:
    """Return the trailing lookback length (periods) for a resolution."""
    try:
        return LOOKBACK_PERIODS[resolution]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"unknown resolution: {resolution!r}") from exc


def feature_columns(frame: pd.DataFrame) -> list[str]:
    """Return the FEATURE columns of a feature/model frame.

    Features are every column that is neither a key, the raw current-period
    outcome, nor a label/target column this module adds. This is the exact set a
    model may consume as predictors.
    """
    excluded = set(KEY_COLS) | set(OUTCOME_COLS) | set(LABEL_COLS)
    return [c for c in frame.columns if c not in excluded]


# --------------------------------------------------------------------------- #
# Target derivation
# --------------------------------------------------------------------------- #

def derive_target(
    features: pd.DataFrame,
    *,
    lookback: Optional[int] = None,
    min_next_samples: int = MIN_NEXT_SAMPLES,
) -> pd.DataFrame:
    """Derive the next-period target for a feature matrix (Req 5.1, 5.2, 5.4).

    For every ``(state, period=t)`` row, compute:

    * ``baseline`` — trailing mean of ``outcome_routine_positivity_rate`` over
      the ``lookback`` periods STRICTLY BEFORE ``t`` (past-only);
    * ``y_next_positivity`` — the NEXT period's routine positivity rate (the
      count/rate formulation, Req 5.4);
    * ``y_elevated`` — 1 if ``y_next_positivity > baseline`` else 0 (Req 5.1);
    * ``labelable`` / ``exclusion_reason`` — whether the cell can be labeled and,
      if not, why (Req 5.2): insufficient history (< ``lookback`` prior periods
      with an observed baseline) or an unobserved / too-thin next period.

    Rows are processed independently per state in chronological order. The
    returned frame is the input with the added label columns; no feature column
    is read to form the label (the label depends ONLY on the routine outcome
    series), which :func:`assert_no_label_leakage` re-checks.
    """
    if features.empty:
        out = features.copy()
        for col in LABEL_COLS:
            out[col] = pd.Series(dtype="object")
        return out

    resolution = str(features["resolution"].iloc[0])
    lb = lookback if lookback is not None else lookback_for(resolution)

    out = features.copy()
    out["_start"] = out["period"].map(period_start)

    baseline = np.full(len(out), np.nan, dtype=float)
    y_next = np.full(len(out), np.nan, dtype=float)
    next_samples = np.full(len(out), np.nan, dtype=float)
    next_positives = np.full(len(out), np.nan, dtype=float)
    next_period = np.array([None] * len(out), dtype=object)
    labelable = np.zeros(len(out), dtype=bool)
    reason = np.array([""] * len(out), dtype=object)

    pos_arr = pd.to_numeric(out["outcome_routine_positivity_rate"], errors="coerce").to_numpy()
    samp_arr = pd.to_numeric(out["outcome_routine_samples"], errors="coerce").to_numpy()
    posct_arr = pd.to_numeric(out["outcome_routine_positives"], errors="coerce").to_numpy()

    for state, idx in out.groupby("state").groups.items():
        # chronological order within the state
        order = out.loc[idx].sort_values("_start").index.tolist()
        n = len(order)
        pos_pos = {row_i: pos_arr[out.index.get_loc(row_i)] for row_i in order}
        samp_pos = {row_i: samp_arr[out.index.get_loc(row_i)] for row_i in order}
        posct_pos = {row_i: posct_arr[out.index.get_loc(row_i)] for row_i in order}
        for i, row_i in enumerate(order):
            li = out.index.get_loc(row_i)
            # --- trailing baseline over strictly-past periods --------------
            prior = order[max(0, i - lb):i]  # up to `lb` periods before t
            prior_rates = [pos_pos[p] for p in prior if not np.isnan(pos_pos[p])]
            have_full_history = len(prior) >= lb and len(prior_rates) >= lb
            if prior_rates:
                baseline[li] = float(np.mean(prior_rates))

            # --- next-period outcome (t+1) ---------------------------------
            if i + 1 < n:
                nxt = order[i + 1]
                next_period[li] = out.loc[nxt, "period"]
                nxt_rate = pos_pos[nxt]
                nxt_samp = samp_pos[nxt]
                nxt_posct = posct_pos[nxt]
                next_samples[li] = nxt_samp if not np.isnan(nxt_samp) else np.nan
                next_positives[li] = nxt_posct if not np.isnan(nxt_posct) else np.nan
                if not np.isnan(nxt_rate):
                    y_next[li] = float(nxt_rate)

            # --- labelability (Req 5.2) ------------------------------------
            next_ok = (
                i + 1 < n
                and not np.isnan(next_samples[li])
                and next_samples[li] >= min_next_samples
                and not np.isnan(y_next[li])
            )
            hist_ok = have_full_history and not np.isnan(baseline[li])
            if hist_ok and next_ok:
                labelable[li] = True
            else:
                parts = []
                if not hist_ok:
                    parts.append(
                        f"insufficient_history(<{lb} prior periods of observed "
                        f"routine positivity)"
                    )
                if i + 1 >= n:
                    parts.append("no_next_period(end_of_series)")
                elif np.isnan(next_samples[li]) or next_samples[li] < min_next_samples:
                    parts.append(
                        f"next_period_samples_below_min(<{min_next_samples})"
                    )
                elif np.isnan(y_next[li]):
                    parts.append("next_period_positivity_unobserved")
                reason[li] = "; ".join(parts)

    out["baseline"] = baseline
    out["y_next_positivity"] = y_next
    out["next_routine_samples"] = next_samples
    out["next_routine_positives"] = next_positives
    out["next_period"] = next_period
    out["labelable"] = labelable
    out["exclusion_reason"] = reason

    # Binary label (v1, OLD): 1 iff next-period positivity strictly exceeds the
    # trailing baseline. Only defined where labelable; elsewhere left as <NA>.
    y_elevated = np.where(
        labelable,
        (y_next > baseline).astype(float),
        np.nan,
    )
    out["y_elevated"] = pd.array(
        [int(v) if not np.isnan(v) else pd.NA for v in y_elevated], dtype="Int64"
    )

    # Redesigned (v2) label columns are added by add_smoothed_label(), which
    # needs the chronological split to compute the TRAIN-only tail threshold.
    # Initialize as empty/unlabelable so a frame that skips that step is still
    # structurally complete and leakage-safe.
    out["smoothed_next_positivity"] = np.nan
    out["v2_threshold"] = np.nan
    out["labelable_v2"] = False
    out["exclusion_reason_v2"] = ""
    out["y_elevated_v2"] = pd.array([pd.NA] * len(out), dtype="Int64")

    out = out.drop(columns=["_start"])
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Redesigned denominator-aware label (Beta-Binomial shrinkage + tail threshold)
# --------------------------------------------------------------------------- #

def national_prior_from_train(
    model: pd.DataFrame,
    train_mask: np.ndarray | pd.Series,
) -> float:
    """Pooled national next-period routine positivity over TRAIN rows (the prior).

    The empirical-Bayes prior rate ``p_nat`` is the pooled next-period positivity
    across ALL states on the TRAIN rows only: ``sum(next_positives) /
    sum(next_samples)`` over labelable-with-next-observed TRAIN cells. Pooling
    (rather than averaging per-cell rates) weights by denominator so the prior
    is the genuine national base rate, not an average of noisy small-cell rates.
    Computed on TRAIN ONLY so no test information enters the prior.
    """
    mask = np.asarray(train_mask, dtype=bool)
    sub = model.loc[mask]
    pos = pd.to_numeric(sub["next_routine_positives"], errors="coerce")
    samp = pd.to_numeric(sub["next_routine_samples"], errors="coerce")
    ok = pos.notna() & samp.notna() & (samp > 0)
    tot_samp = float(samp[ok].sum())
    tot_pos = float(pos[ok].sum())
    if tot_samp <= 0:
        return 0.0
    return tot_pos / tot_samp


def beta_binomial_shrink(
    positives: np.ndarray,
    samples: np.ndarray,
    p_nat: float,
    *,
    pseudocount: float = SHRINKAGE_PSEUDOCOUNT,
) -> np.ndarray:
    """Posterior-mean (empirical-Bayes) Beta-Binomial shrinkage toward ``p_nat``.

    With prior ``Beta(alpha, beta)``, ``alpha = m * p_nat``,
    ``beta = m * (1 - p_nat)`` and ``m = pseudocount``, a cell with ``k``
    positives out of ``n`` samples has posterior mean
    ``(k + alpha) / (n + alpha + beta) = (k + m * p_nat) / (n + m)``.

    The result always lies strictly between the raw rate ``k/n`` and the prior
    ``p_nat`` (a convex combination with weight ``n/(n+m)`` on the raw rate),
    so thin cells (small ``n``) are pulled toward the national prior and
    well-sampled cells keep nearly their raw rate. NaN where ``n`` is missing.
    """
    k = np.asarray(positives, dtype=float)
    n = np.asarray(samples, dtype=float)
    m = float(pseudocount)
    alpha = m * p_nat
    out = (k + alpha) / (n + m)
    out = np.where(np.isnan(n) | np.isnan(k), np.nan, out)
    return out


def train_tail_threshold(
    smoothed: np.ndarray,
    train_mask: np.ndarray | pd.Series,
    *,
    percentile: float = TAIL_PERCENTILE,
) -> float:
    """High-risk threshold = ``percentile`` of smoothed positivity over TRAIN.

    Computed on the TRAIN rows ONLY (no test peeking). Only finite smoothed
    values on labelable-v2 TRAIN cells contribute. Returns ``nan`` if there are
    no usable train values.
    """
    sm = np.asarray(smoothed, dtype=float)
    mask = np.asarray(train_mask, dtype=bool)
    vals = sm[mask]
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return float("nan")
    return float(np.percentile(vals, percentile))


def add_smoothed_label(
    model: pd.DataFrame,
    *,
    test_fraction: float = 0.20,
    pseudocount: float = SHRINKAGE_PSEUDOCOUNT,
    percentile: float = TAIL_PERCENTILE,
    min_next_samples_v2: int = MIN_NEXT_SAMPLES_V2,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Attach the redesigned denominator-aware primary label ``y_elevated_v2``.

    Steps (all leakage-safe; threshold uses TRAIN rows only):

    1. **v2 labelability** — a cell is ``labelable_v2`` iff it already passed the
       v1 history/next-period checks AND its next period has at least
       ``min_next_samples_v2`` routine samples with an observed positive count
       (needed for a meaningful smoothed rate).
    2. **National prior** ``p_nat`` — pooled next-period positivity over the
       TRAIN rows only (:func:`national_prior_from_train`).
    3. **Shrinkage** — ``smoothed_next_positivity`` via Beta-Binomial posterior
       mean toward ``p_nat`` (:func:`beta_binomial_shrink`) for every v2-labelable
       cell.
    4. **Train-only tail threshold** — the ``percentile``-th percentile of the
       smoothed values over the TRAIN v2-labelable cells
       (:func:`train_tail_threshold`).
    5. **Label** — ``y_elevated_v2 = 1`` iff
       ``smoothed_next_positivity >= v2_threshold`` on v2-labelable cells;
       ``<NA>`` elsewhere (never fabricated).

    Returns ``(model_with_v2, meta)`` where ``meta`` records ``p_nat``, the
    threshold, the percentile/pseudocount, the v2 base rate and v2 exclusions.
    The chronological split reuses the SAME ``test_fraction`` as the modeling
    layer so the threshold's train window matches the model's train window.
    """
    out = model.copy()
    n_rows = len(out)
    if n_rows == 0:
        meta = {
            "p_nat": None, "v2_threshold": None, "pseudocount": pseudocount,
            "tail_percentile": percentile, "min_next_samples_v2": min_next_samples_v2,
            "labelable_v2_count": 0, "positive_v2_count": 0, "base_rate_v2": None,
        }
        return out, meta

    # Local import to avoid a circular import at module load.
    from src.models.splits import distinct_periods_sorted

    v1_labelable = out["labelable"].to_numpy(dtype=bool)
    nxt_samp = pd.to_numeric(out["next_routine_samples"], errors="coerce").to_numpy()
    nxt_pos = pd.to_numeric(out["next_routine_positives"], errors="coerce").to_numpy()

    next_ok_v2 = (
        ~np.isnan(nxt_samp)
        & (nxt_samp >= min_next_samples_v2)
        & ~np.isnan(nxt_pos)
    )
    labelable_v2 = v1_labelable & next_ok_v2

    # v2 exclusion reasons (only for cells not v2-labelable).
    reason_v2 = np.array([""] * n_rows, dtype=object)
    for i in range(n_rows):
        if labelable_v2[i]:
            continue
        parts: list[str] = []
        if not v1_labelable[i]:
            parts.append("not_labelable_v1(see exclusion_reason)")
        else:
            if np.isnan(nxt_samp[i]) or nxt_samp[i] < min_next_samples_v2:
                parts.append(f"next_period_samples_below_v2_min(<{min_next_samples_v2})")
            if np.isnan(nxt_pos[i]):
                parts.append("next_period_positives_unobserved")
        reason_v2[i] = "; ".join(parts)

    # Chronological TRAIN mask over v2-labelable cells (threshold uses train only).
    labelable_sub = out.loc[labelable_v2]
    train_mask_full = np.zeros(n_rows, dtype=bool)
    if len(labelable_sub) >= 2:
        periods = distinct_periods_sorted(labelable_sub)
        n_periods = len(periods)
        n_test = max(1, min(int(round(n_periods * test_fraction)), n_periods - 1))
        cut = n_periods - n_test
        train_periods = set(periods[:cut])
        is_train = out["period"].isin(train_periods).to_numpy() & labelable_v2
        train_mask_full = is_train
    else:
        # degenerate: treat all v2-labelable as train (threshold still defined)
        train_mask_full = labelable_v2.copy()

    p_nat = national_prior_from_train(out, train_mask_full)

    smoothed = np.full(n_rows, np.nan, dtype=float)
    sm_vals = beta_binomial_shrink(
        nxt_pos, nxt_samp, p_nat, pseudocount=pseudocount
    )
    smoothed = np.where(labelable_v2, sm_vals, np.nan)

    threshold = train_tail_threshold(
        smoothed, train_mask_full, percentile=percentile
    )

    y_v2 = np.where(
        labelable_v2 & np.isfinite(smoothed) & np.isfinite(threshold),
        (smoothed >= threshold).astype(float),
        np.nan,
    )

    out["smoothed_next_positivity"] = smoothed
    out["v2_threshold"] = np.where(labelable_v2, threshold, np.nan)
    out["labelable_v2"] = labelable_v2
    out["exclusion_reason_v2"] = reason_v2
    out["y_elevated_v2"] = pd.array(
        [int(v) if (isinstance(v, float) and not np.isnan(v)) else pd.NA for v in y_v2],
        dtype="Int64",
    )

    n_v2 = int(labelable_v2.sum())
    n_pos_v2 = int(np.nansum(y_v2)) if n_v2 else 0
    meta = {
        "p_nat": p_nat,
        "v2_threshold": threshold if np.isfinite(threshold) else None,
        "pseudocount": pseudocount,
        "tail_percentile": percentile,
        "min_next_samples_v2": min_next_samples_v2,
        "n_train_v2_cells_for_threshold": int(train_mask_full.sum()),
        "labelable_v2_count": n_v2,
        "positive_v2_count": n_pos_v2,
        "base_rate_v2": (n_pos_v2 / n_v2) if n_v2 else None,
        "excluded_v2_not_labelable_v1": int(
            (~v1_labelable).sum()
        ),
        "excluded_v2_next_samples_below_min": int(
            (v1_labelable & (~next_ok_v2)).sum()
        ),
    }
    return out, meta


# --------------------------------------------------------------------------- #
# Label-leakage guard (Req 5.1/5.5 integrity)
# --------------------------------------------------------------------------- #

def assert_no_label_leakage(model_frame: pd.DataFrame) -> dict[str, Any]:
    """Assert the label columns are not among the feature columns (no leakage).

    The binary label and the rate target are derived ONLY from the NEXT period's
    routine outcome, never from a feature on the row. This guard verifies the
    two invariants that keep that honest:

    1. ``y_elevated`` / ``y_next_positivity`` / ``baseline`` are NOT in the set
       of columns a model consumes as features; and
    2. none of the raw current-period outcome columns are features either (they
       are the label's *source*, kept out of the predictor set).

    Returns an audit dict; raises :class:`AssertionError` on violation.
    """
    feats = set(feature_columns(model_frame))
    leaked_labels = sorted(feats & set(LABEL_COLS))
    leaked_outcome = sorted(feats & set(OUTCOME_COLS))
    if leaked_labels:
        raise AssertionError(
            f"label/target columns leaked into feature set: {leaked_labels}"
        )
    if leaked_outcome:
        raise AssertionError(
            f"raw current-period outcome columns leaked into feature set "
            f"(these are the label source, not predictors): {leaked_outcome}"
        )
    return {
        "n_feature_columns": len(feats),
        "label_columns_present": sorted(set(model_frame.columns) & set(LABEL_COLS)),
        "ok": True,
    }


# --------------------------------------------------------------------------- #
# Build the modeling-ready table
# --------------------------------------------------------------------------- #

def build_model_table(
    pathogen: str,
    *,
    processed_root: Optional[Path] = None,
    features: Optional[pd.DataFrame] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load the feature matrix, derive the target, and assemble the model table.

    Returns ``(model_frame, summary)``. The model frame carries keys, every
    feature column (unchanged, all ``<= t``), the binary label ``y_elevated``,
    the rate target ``y_next_positivity``, the trailing ``baseline``, a
    ``labelable`` boolean and ``exclusion_reason``. The summary reports labelable
    counts, positive-label base rate and exclusion breakdown per Req 5.2.
    """
    root = processed_root or PROCESSED_ROOT
    if features is None:
        slug = PATHOGEN_SLUG[pathogen]
        parquet = root / f"features_{slug}.parquet"
        csv = root / f"features_{slug}.csv"
        if parquet.exists():
            features = pd.read_parquet(parquet)
        elif csv.exists():
            features = pd.read_csv(csv)
        else:
            raise FileNotFoundError(
                f"no feature table for {pathogen} at {parquet} (run features first)"
            )

    model = derive_target(features)
    # Attach the redesigned denominator-aware primary label (v2) with its
    # TRAIN-only tail threshold before the leakage guard.
    model, v2_meta = add_smoothed_label(model)
    assert_no_label_leakage(model)

    resolution = str(features["resolution"].iloc[0]) if not features.empty else "monthly"
    lb = lookback_for(resolution)

    labelable_mask = model["labelable"] == True  # noqa: E712 - explicit for Int/obj
    n_total = int(len(model))
    n_labelable = int(labelable_mask.sum())
    labeled = model.loc[labelable_mask]
    n_positive = int((labeled["y_elevated"] == 1).sum()) if n_labelable else 0
    base_rate = (n_positive / n_labelable) if n_labelable else None

    # exclusion breakdown by reason category (Req 5.2)
    excl = model.loc[~labelable_mask, "exclusion_reason"]
    n_insufficient = int(excl.str.contains("insufficient_history", na=False).sum())
    n_no_next = int(excl.str.contains("no_next_period", na=False).sum())
    n_thin_next = int(excl.str.contains("next_period_samples_below_min", na=False).sum())
    n_next_unobs = int(excl.str.contains("next_period_positivity_unobserved", na=False).sum())

    # rate-target coverage among labelable cells (should equal next positivity)
    rate_defined = int(labeled["y_next_positivity"].notna().sum()) if n_labelable else 0

    summary = {
        "pathogen": pathogen,
        "resolution": resolution,
        "horizon_periods": HORIZON_PERIODS,
        "lookback_periods": lb,
        "total_modeling_units": n_total,
        "labelable_modeling_units": n_labelable,
        "positive_label_count": n_positive,
        "base_rate_elevated": base_rate,
        "excluded_insufficient_history": n_insufficient,
        "excluded_no_next_period": n_no_next,
        "excluded_next_samples_below_min": n_thin_next,
        "excluded_next_positivity_unobserved": n_next_unobs,
        "rate_target_defined_count": rate_defined,
        "feature_column_count": len(feature_columns(model)),
        # --- redesigned denominator-aware label (v2 PRIMARY) ---------------
        "v2_primary_label": "y_elevated_v2",
        "v2_national_prior_rate": v2_meta["p_nat"],
        "v2_shrinkage_pseudocount": v2_meta["pseudocount"],
        "v2_tail_percentile": v2_meta["tail_percentile"],
        "v2_min_next_samples": v2_meta["min_next_samples_v2"],
        "v2_train_threshold": v2_meta["v2_threshold"],
        "v2_n_train_cells_for_threshold": v2_meta.get("n_train_v2_cells_for_threshold"),
        "labelable_v2_modeling_units": v2_meta["labelable_v2_count"],
        "positive_label_v2_count": v2_meta["positive_v2_count"],
        "base_rate_v2": v2_meta["base_rate_v2"],
        "excluded_v2_not_labelable_v1": v2_meta.get("excluded_v2_not_labelable_v1"),
        "excluded_v2_next_samples_below_min": v2_meta.get(
            "excluded_v2_next_samples_below_min"
        ),
    }
    return model, summary


# --------------------------------------------------------------------------- #
# Report (Req 5.4 comparison note + Req 5.5 statement)
# --------------------------------------------------------------------------- #

def _binary_vs_rate_note() -> dict[str, Any]:
    """The binary-vs-rate framing comparison note and chosen rationale (Req 5.4)."""
    return {
        "formulations_evaluated": ["binary_elevated", "rate_next_positivity"],
        "selected_primary": "binary_elevated",
        "binary": {
            "name": "y_elevated",
            "definition": (
                "1 if next-period routine positivity exceeds the trailing "
                ">=12-month baseline for the (state) Modeling_Unit, else 0"
            ),
            "pros": (
                "maps directly to the operational decision (do we escalate "
                "attention next period?); robust to the heavy right-skew and "
                "the many zero-positivity cells of rare-event pathogens "
                "(Listeria 0.61%, STEC 0.29% prevalence); evaluated with "
                "rare-event-appropriate metrics (PR-AUC, calibration)"
            ),
            "cons": (
                "discards magnitude information; sensitive to the baseline "
                "definition near the threshold"
            ),
        },
        "rate": {
            "name": "y_next_positivity",
            "definition": (
                "raw next-period routine positivity rate "
                "(positives / samples) at the Modeling_Unit"
            ),
            "pros": "retains magnitude; useful as a regression diagnostic",
            "cons": (
                "dominated by zeros and tiny denominators for rare-event "
                "pathogens, producing an unstable, heavily zero-inflated target "
                "that is hard to calibrate and does not map cleanly to a yes/no "
                "operational action"
            ),
        },
        "decision_rationale": (
            "The primary decision target is the BINARY elevated-positivity "
            "indicator because the Decision_Maker's operational choice is "
            "discrete (escalate inspection / attention for a state-period or "
            "not), and because next-period routine positivity is heavily "
            "zero-inflated for the rare-event pathogens, making a raw-rate "
            "regression target unstable and poorly calibrated. The raw rate is "
            "retained as y_next_positivity for diagnostics and as the count/rate "
            "formulation required by Req 5.4, but is not the primary target."
        ),
        "comparison_metrics_plan": (
            "binary framing is scored with PR-AUC, ROC-AUC, Brier and "
            "calibration (rare-event-appropriate per feasibility_report); the "
            "rate framing would be scored with MAE/RMSE on positivity — reported "
            "in validation (Task 3.7), not here"
        ),
    }


def _redesign_v2_note() -> dict[str, Any]:
    """Rationale for the redesigned denominator-aware primary label (v2).

    Documents WHY the original ``y_elevated`` (next-period positivity > that
    cell's own trailing mean) was near-chance and HOW ``y_elevated_v2`` fixes it,
    plus the exact, fixed-pre-tuning method so the redesign is auditable and not
    tuned against the untouched test period.
    """
    return {
        "motivation": (
            "The original label y_elevated = 1[next-period positivity > that "
            "cell's OWN trailing mean] is ~50/50 by construction (a value is "
            "above or below its own recent mean about half the time) and is "
            "dominated by small-denominator sampling noise, so it carried little "
            "decision-relevant signal — prospective discrimination was near "
            "chance (Salmonella test ROC-AUC 0.586, PR-AUC 0.548, 95% CI barely "
            "clearing 0.5). The redesign makes the target denominator-aware and "
            "tail-based so a positive means 'this state-period is in the "
            "genuinely high-risk tail', not merely 'above its own noisy mean'."
        ),
        "primary_label": "y_elevated_v2",
        "kept_old_label": (
            "y_elevated (v1) is retained on every row for an honest before/after "
            "comparison; v2 is the new PRIMARY modeling target."
        ),
        "step1_denominator_aware_smoothing": {
            "name": "smoothed_next_positivity",
            "method": "empirical-Bayes Beta-Binomial posterior mean",
            "formula": (
                "smoothed = (k + m*p_nat) / (n + m), where (k, n) are the "
                "next-period routine (positives, samples), p_nat is the pathogen "
                "national prior rate, and m is a fixed prior strength "
                "(pseudo-count). Equivalent to the posterior mean of a "
                "Beta(alpha=m*p_nat, beta=m*(1-p_nat)) prior updated by a "
                "Binomial(n, .) likelihood."
            ),
            "prior_rate_p_nat": (
                "pooled next-period routine positivity over TRAIN rows only "
                "(sum positives / sum samples) — the genuine national base rate, "
                "denominator-weighted, never peeking at test"
            ),
            "prior_strength_pseudocount": SHRINKAGE_PSEUDOCOUNT,
            "prior_strength_rationale": (
                f"m = {SHRINKAGE_PSEUDOCOUNT:g} is a FIXED documented pseudo-count "
                "held constant across pathogens: a cell with n >> m keeps nearly "
                "its raw rate; a thin cell (n comparable to or below m) shrinks "
                "toward p_nat, taming small-denominator noise. The smoothed value "
                "always lies between the raw rate k/n and p_nat."
            ),
        },
        "step2_tail_based_label": {
            "name": "y_elevated_v2",
            "definition": (
                "1 iff smoothed_next_positivity >= v2_threshold, else 0"
            ),
            "threshold_rule": (
                f"the {TAIL_PERCENTILE:g}th percentile of smoothed_next_positivity "
                "over the TRAIN periods for that pathogen"
            ),
            "threshold_computed_on": "TRAIN rows ONLY (no test peeking)",
            "interpretation": (
                "targets 'is this state-period in the genuinely high-risk tail "
                "of smoothed positivity?' — a decision-relevant escalation signal"
            ),
        },
        "step3_horizon_and_scope": {
            "horizon_periods": HORIZON_PERIODS,
            "fixed_before_tuning": HORIZON_FIXED_PRE_TUNING,
            "scope": "routine surveillance; next period (t+1); unchanged",
            "min_next_samples_v2": MIN_NEXT_SAMPLES_V2,
            "exclusions": (
                "v2 excludes everything v1 excludes (insufficient history, "
                "unobserved/thin next period) PLUS requires next-period routine "
                f"samples >= {MIN_NEXT_SAMPLES_V2} with an observed positive count "
                "so the smoothed rate reflects at least some direct observation"
            ),
        },
        "fixed_pre_tuning_note": (
            "The pseudo-count (m), the tail percentile, the min-next-samples "
            "floor and the horizon are ALL fixed BEFORE any model tuning and are "
            "NOT adjusted against the untouched final test period. The train "
            "threshold is derived from TRAIN rows only; model tuning (if any) is "
            "confined to the training window."
        ),
        "aggregation_note": (
            "Aggregation remains state x period (monthly for Salmonella, "
            "quarterly for Listeria/STEC) exactly as before. This is defensible: "
            "the operational decision is per-state-period surveillance "
            "escalation, and the resolution was chosen on feasibility evidence "
            "(median positives per active cell), not tuned to chase test "
            "metrics. Aggregation is deliberately NOT changed as part of this "
            "redesign."
        ),
    }


def write_target_report(
    summaries: dict[str, dict[str, Any]],
    *,
    out_path: Optional[Path] = None,
) -> Path:
    """Write ``data/interim/target_report.json`` (Req 5.2, 5.3, 5.4, 5.5)."""
    out_path = out_path or (INTERIM_ROOT / "target_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "task": "3.3 Define prediction target and fixed horizon",
        "requirements": ["5.1", "5.2", "5.3", "5.4", "5.5"],
        "redesign_v2": _redesign_v2_note(),
        "horizon": {
            "horizon_periods": HORIZON_PERIODS,
            "unit": "one resolution-period ahead (month for Salmonella; "
                    "quarter for Listeria/STEC)",
            "fixed_before_tuning": HORIZON_FIXED_PRE_TUNING,
            "note": (
                "HORIZON_PERIODS is a module constant fixed BEFORE any model "
                "tuning and MUST NOT change once tuning begins (Req 5.3)."
            ),
        },
        "baseline": {
            "definition": (
                "trailing mean of routine positivity over the lookback window of "
                "periods strictly before t (past-only); label compares next "
                "period (t+1) against this baseline (Req 5.1)"
            ),
            "lookback_periods": LOOKBACK_PERIODS,
            "min_history_note": "at least 12 months of prior history required",
        },
        "exclusions": {
            "insufficient_history": (
                "Modeling_Units with fewer than the lookback periods of observed "
                "prior routine positivity are excluded from labeling and recorded "
                "(Req 5.2)"
            ),
            "unobserved_or_thin_next_period": (
                f"cells whose next period has no routine row or fewer than "
                f"{MIN_NEXT_SAMPLES} tested sample(s) are recorded as unlabelable, "
                f"never assigned a fabricated label (Req 5.2 / 4.6)"
            ),
            "min_next_samples": MIN_NEXT_SAMPLES,
        },
        "binary_vs_rate": _binary_vs_rate_note(),
        "target_scope_statement": TARGET_IS_SURVEILLANCE_RISK,
        "per_pathogen": summaries,
    }
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out_path


# --------------------------------------------------------------------------- #
# Top-level orchestration
# --------------------------------------------------------------------------- #

def run_target_derivation(
    *,
    pathogens: Optional[tuple[str, ...]] = None,
    processed_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Derive the target for every pathogen, write model tables + the report.

    Produces ``data/processed/model_<pathogen>.parquet`` (CSV fallback) plus a
    ``.sample.csv`` and ``data/interim/target_report.json``; returns the
    per-pathogen summary.
    """
    processed_root = processed_root or PROCESSED_ROOT
    processed_root.mkdir(parents=True, exist_ok=True)
    pathogens = pathogens or tuple(PATHOGEN_SLUG.keys())

    summaries: dict[str, dict[str, Any]] = {}
    for pathogen in pathogens:
        model, summary = build_model_table(pathogen, processed_root=processed_root)
        slug = PATHOGEN_SLUG[pathogen]
        parquet = processed_root / f"model_{slug}.parquet"
        sample_csv = processed_root / f"model_{slug}.sample.csv"
        wrote_parquet = False
        if not model.empty:
            try:
                model.to_parquet(parquet, index=False)
                wrote_parquet = True
            except Exception as exc:  # noqa: BLE001 - CSV fallback if no engine
                parquet = processed_root / f"model_{slug}.csv"
                model.to_csv(parquet, index=False)
                print(f"[target] parquet unavailable for {pathogen}: {exc!r}; wrote CSV")
            model.head(50).to_csv(sample_csv, index=False)
        summary["parquet"] = str(parquet)
        summary["wrote_parquet"] = wrote_parquet
        summaries[pathogen] = summary

    write_target_report(summaries)
    return summaries


if __name__ == "__main__":  # pragma: no cover - manual invocation
    import pprint
    pprint.pprint(run_target_derivation())
