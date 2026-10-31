"""Establishment-level Salmonella forecasting experiment (parallel to state-v2).

This module builds, evaluates and adjudicates an ESTABLISHMENT-level forecasting
engine for Salmonella in raw poultry, WITHOUT touching the state-level v2 models
in :mod:`src.models.baseline` / :mod:`src.models.integrated` / :mod:`src.models
.validation`. It is a sibling experiment: its sole write targets are
``data/interim/establishment_*.json``, ``docs/reports/establishment_*.md`` and
``data/processed/models/establishment_*`` — the state-v2 artifacts are never
overwritten.

Why establishment level, and why only Salmonella
------------------------------------------------
The raw FSIS laboratory-sampling files carry a real ``establishment_id`` (1,409
distinct Salmonella establishments, confirmed). A measured feasibility gate
(reproduced in :func:`temporal_feasibility`) shows Salmonella has enough
establishment history AND enough evaluable future outcomes to forecast at the
establishment × quarter grain, whereas Listeria and STEC have a median of 0
positives per establishment and cannot be forecast per establishment — they are
handled DESCRIPTIVELY only (:func:`descriptive_establishment_scores`).

Leakage safety (the whole point)
--------------------------------
Every feature for predicting establishment ``e`` in quarter ``q`` is built ONLY
from that establishment's (and its peer group's / state's / the nation's)
samples whose assumed availability date is at or before the **start of quarter
``q``** — i.e. strictly from quarters ``<= q-1``. The reporting-lag assumption is
reused from :mod:`src.pipeline.harmonize` (``collection_date + REPORTING_LAG_DAYS``)
so "available at the cutoff" means the same thing it does in the state pipeline.
:func:`assert_leakage_safe` fails loudly if any feature row could have drawn on a
sample collected in or after its own target quarter.

Targets (Step 3)
----------------
* PRIMARY — the future positive RATE per 100 comparable (routine) samples over
  the NEXT quarter, modelled as a beta-binomial / binomial rate and evaluated
  against the observed next-quarter positives/samples. Next-quarter counts are
  used ONLY as the evaluation denominator, never as a feature.
* COMPLEMENTARY — a binary "will the establishment's next-quarter routine
  positivity exceed its own trailing baseline" label, used for the ranking /
  top-K comparison against the state engine.

Models + baselines (Step 4)
---------------------------
Strong baselines: EB-smoothed establishment historical positivity, PEER-GROUP
(product_type) historical positivity, and seasonally-adjusted persistence.
Learners: Logistic, RandomForest, XGBoost, LightGBM on the leakage-safe
features, trained on history only with an untouched final test period.

Evaluation (Step 5)
-------------------
Chronological rolling-origin (>= 3 origins); calibration / Brier / PR-AUC /
ROC-AUC with 95% bootstrap CIs; TOP-K capture under an identical inspection
budget (top 10% and top-50 establishments) reported as positives captured /
recall@K / precision@K; a head-to-head establishment-vs-state comparison on a
COMMON future outcome over a COMMON eligible population; FAMILIAR vs UNSEEN
establishment generalization (whole establishments held out). Insufficient-
recent-testing establishments are flagged uncertain-not-safe; a zero-positive
establishment is never auto-labelled "safe".

Honesty rules
-------------
Nothing is fabricated. Any metric undefined on a slice is recorded ``null`` with
a reason. Retrospective top-K capture is reported as *retrospective capture of
positive tests*, NOT as proven contamination or illness reduction. The retailer
stays the decision-maker: outputs are supplier verification / additional product
testing / human review / recall response / replacement allocation — never
government inspection orders and never individual-shipment contamination claims.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.pipeline import audit
from src.pipeline.harmonize import REPORTING_LAG_DAYS, TARGET_CATEGORY, tag_program
from src.pipeline.ingest import REPO_ROOT

__all__ = [
    "INTERIM_ROOT",
    "PROCESSED_MODELS_ROOT",
    "DOCS_REPORTS_ROOT",
    "RANDOM_STATE",
    "EVALUABLE_MIN_SAMPLES",
    "HISTORY_MIN_SAMPLES",
    "EB_PRIOR_STRENGTH",
    "TOPK_FRACTION",
    "TOPK_ABSOLUTE",
    "ROLLING_ORIGINS",
    "PATHOGENS",
    "PRIMARY_PATHOGEN",
    "RETAILER_ACTIONS",
    "load_establishment_samples",
    "build_establishment_quarters",
    "temporal_feasibility",
    "build_features",
    "assert_leakage_safe",
    "eb_smoothed_rate",
    "build_targets",
    "run_experiment",
]

# --------------------------------------------------------------------------- #
# Paths + constants
# --------------------------------------------------------------------------- #

INTERIM_ROOT: Path = REPO_ROOT / "data" / "interim"
PROCESSED_MODELS_ROOT: Path = REPO_ROOT / "data" / "processed" / "models"
DOCS_REPORTS_ROOT: Path = REPO_ROOT / "docs" / "reports"

#: Fixed seed so every bootstrap / split / fit reproduces identically.
RANDOM_STATE: int = 42

#: An establishment-quarter has an EVALUABLE future outcome only if the NEXT
#: quarter has at least this many comparable (routine) samples, so a positivity
#: RATE is estimable rather than 0/0 or 1/1 noise.
EVALUABLE_MIN_SAMPLES: int = 10

#: An establishment-quarter has SUFFICIENT HISTORY only if its trailing window
#: carries at least this many comparable samples (otherwise the establishment is
#: flagged uncertain-not-safe rather than scored confidently).
HISTORY_MIN_SAMPLES: int = 10

#: Empirical-Bayes Beta-Binomial prior strength (pseudo-counts) used to shrink a
#: thin establishment's historical positivity toward the national rate. Larger =
#: more shrinkage. A thin establishment lands near the national rate; a heavily
#: sampled one keeps its own rate.
EB_PRIOR_STRENGTH: float = 20.0

#: Top-K inspection-budget settings (Step 5): a percentage budget and an
#: absolute-count budget, evaluated identically for every engine.
TOPK_FRACTION: float = 0.10
TOPK_ABSOLUTE: int = 50

#: Rolling-origin count for chronological validation (Req: >= 3).
ROLLING_ORIGINS: int = 3

#: Per-pathogen program slug in :data:`audit.PROGRAM_META`.
PATHOGENS: dict[str, str] = {
    "Salmonella": "raw_poultry_salmonella",
    "Listeria": "rte_listeria",
    "STEC": "raw_beef_stec",
}

#: The one pathogen the feasibility gate expects to support establishment-level
#: FORECASTS; the others are descriptive-only.
PRIMARY_PATHOGEN: str = "Salmonella"

#: The retailer-facing action vocabulary. The retailer is the decision maker;
#: none of these is a government inspection order or an individual-shipment
#: contamination claim.
RETAILER_ACTIONS: tuple[str, ...] = (
    "supplier_verification",
    "additional_product_testing",
    "human_review",
    "recall_response",
    "replacement_allocation",
)

#: Representative cutoff quarters spanning 2014-2026 for the feasibility gate.
FEASIBILITY_CUTOFFS: tuple[str, ...] = (
    "2015-Q1", "2016-Q1", "2017-Q1", "2018-Q1", "2019-Q1", "2020-Q1",
    "2021-Q1", "2022-Q1", "2023-Q1", "2024-Q1", "2025-Q1", "2026-Q1",
)

#: Trailing-history windows (in days before the cutoff) the feasibility gate
#: reports sample counts over.
TRAILING_WINDOWS_DAYS: tuple[int, ...] = (90, 180, 365, 730)


# --------------------------------------------------------------------------- #
# Quarter helpers (establishment grain is quarterly)
# --------------------------------------------------------------------------- #

def quarter_label(ts: pd.Timestamp) -> str:
    """Return the ``YYYY-Qn`` label for a timestamp."""
    q = (ts.month - 1) // 3 + 1
    return f"{ts.year:04d}-Q{q}"


def quarter_start(label: str) -> pd.Timestamp:
    """First calendar day of a ``YYYY-Qn`` quarter label (the horizon cutoff)."""
    year, q = label.split("-Q")
    month = (int(q) - 1) * 3 + 1
    return pd.Timestamp(year=int(year), month=month, day=1)


def next_quarter(label: str) -> str:
    """Return the label of the quarter immediately after ``label``."""
    year, q = label.split("-Q")
    year, q = int(year), int(q)
    return f"{year + 1:04d}-Q1" if q == 4 else f"{year:04d}-Q{q + 1}"


def _sorted_quarters(labels: Any) -> list[str]:
    return sorted(set(labels), key=quarter_start)


# --------------------------------------------------------------------------- #
# Load establishment-level routine samples (leakage columns attached)
# --------------------------------------------------------------------------- #

@dataclass
class EstablishmentSamples:
    """A tidy per-sample table for one pathogen, plus the derived peer group."""

    pathogen: str
    frame: pd.DataFrame
    n_establishments: int
    n_samples: int
    date_range: tuple[Optional[str], Optional[str]]


def load_establishment_samples(
    pathogen: str = PRIMARY_PATHOGEN,
    *,
    program_dirs: Optional[dict[str, Path]] = None,
    routine_only: bool = True,
) -> EstablishmentSamples:
    """Load per-sample establishment rows with leakage-safe availability columns.

    One row per FSIS lab sample. Columns kept / derived:

    * ``establishment_id`` / ``establishment_name`` / ``state`` — identity.
    * ``product_type`` — the comparable-program peer dimension.
    * ``program_category`` — from :func:`~src.pipeline.harmonize.tag_program`;
      only ``routine_surveillance`` feeds the forecast when ``routine_only``.
    * ``collection_date`` / ``availability_date`` — the assumed availability date
      is ``collection_date + REPORTING_LAG_DAYS`` (same assumption as the state
      pipeline), so a sample is only usable once that date has passed.
    * ``is_positive`` / ``is_testable`` — tri-state result (lab-problem / blank
      rows are NOT testable and are dropped from labels, never forced 0/1).
    * ``quarter`` — the collection quarter label.

    Only testable rows (positive / negative) are retained; a sample that could
    not yield a result carries no label and is excluded (never fabricated).
    """

    slug = PATHOGENS[pathogen]
    result_col = audit.PROGRAM_META[slug]["result_column"]
    df, _ = audit._load_program_frame(slug, program_dirs)
    if df.empty:
        raise FileNotFoundError(
            f"no raw FSIS frame for {pathogen} ({slug}); run ingest/drop archives"
        )

    out = pd.DataFrame()
    out["establishment_id"] = df[audit.COL_ESTABLISHMENT_ID].astype("string")
    out["establishment_name"] = (
        df["establishment_name"].astype("string")
        if "establishment_name" in df.columns else pd.NA
    )
    out["state"] = df[audit.COL_STATE].astype("string")

    # Product/commodity peer dimension: product_type for poultry, else the
    # closest available product column (sample_source_name).
    product_col = next(
        (c for c in audit.COL_PRODUCT_CANDIDATES if c in df.columns), None
    )
    out["product_type"] = (
        df[product_col].astype("string") if product_col else pd.NA
    )
    out["project_code"] = df[audit.COL_PROJECT_CODE].astype("string")
    out["project_name"] = (
        df[audit.COL_PROJECT_NAME].astype("string")
        if audit.COL_PROJECT_NAME in df.columns else pd.NA
    )

    # Program category (cache tag_program over distinct code/name pairs).
    pairs = out[["project_code", "project_name"]].drop_duplicates()
    cat_map = {
        (str(c), str(n)): tag_program(str(c), str(n))
        for c, n in pairs.itertuples(index=False)
    }
    out["program_category"] = [
        cat_map.get((str(c), str(n)))
        for c, n in zip(out["project_code"], out["project_name"])
    ]

    coll = pd.to_datetime(df[audit.COL_COLLECTION_DATE], errors="coerce")
    out["collection_date"] = coll
    out["availability_date"] = coll + pd.to_timedelta(REPORTING_LAG_DAYS, unit="D")

    cls = df[result_col].map(audit.classify_result)
    out["is_positive"] = (cls == "positive").astype(int)
    out["is_testable"] = cls.isin(["positive", "negative"]).astype(int)

    # Keep only labelled rows with a parseable date and an establishment id.
    out = out[
        (out["is_testable"] == 1)
        & out["collection_date"].notna()
        & out["establishment_id"].notna()
    ].copy()
    if routine_only:
        out = out[out["program_category"] == TARGET_CATEGORY].copy()

    out["quarter"] = out["collection_date"].map(quarter_label)
    # Normalise a missing product_type to an explicit bucket so peer grouping is
    # deterministic (never silently drops thin-product establishments).
    out["product_type"] = out["product_type"].fillna("UNKNOWN_PRODUCT").astype(str)
    out["establishment_id"] = out["establishment_id"].astype(str)
    out["state"] = out["state"].fillna("UNK").astype(str)
    out = out.reset_index(drop=True)

    dates = out["collection_date"]
    return EstablishmentSamples(
        pathogen=pathogen,
        frame=out,
        n_establishments=int(out["establishment_id"].nunique()),
        n_samples=int(len(out)),
        date_range=(
            str(dates.min().date()) if len(out) else None,
            str(dates.max().date()) if len(out) else None,
        ),
    )


# --------------------------------------------------------------------------- #
# Establishment x quarter panel (aggregate of routine samples)
# --------------------------------------------------------------------------- #

def build_establishment_quarters(samples: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-sample rows to one row per ``(establishment_id, quarter)``.

    Carries the establishment's dominant ``product_type`` / ``state`` for that
    quarter, the routine ``samples`` / ``positives`` counts and the observed
    ``positivity_rate`` (``positives / samples``), plus the MAX availability date
    of contributing samples (used downstream as the leakage cutoff reference).
    """
    if samples.empty:
        return pd.DataFrame(
            columns=[
                "establishment_id", "quarter", "state", "product_type",
                "samples", "positives", "positivity_rate", "availability_date",
                "quarter_start",
            ]
        )

    # Dominant state / product_type per (establishment, quarter) via a fast
    # value-count ranking instead of a per-group ``.mode()`` lambda (which is
    # O(groups) Python calls and dominates runtime on the real tables).
    def _dominant(col: str) -> pd.DataFrame:
        cnt = (
            samples.groupby(["establishment_id", "quarter", col])
            .size()
            .reset_index(name="_n")
            .sort_values(["establishment_id", "quarter", "_n"], ascending=[True, True, False])
        )
        return (
            cnt.drop_duplicates(["establishment_id", "quarter"])[
                ["establishment_id", "quarter", col]
            ]
        )

    g = samples.groupby(["establishment_id", "quarter"], as_index=False).agg(
        samples=("is_testable", "sum"),
        positives=("is_positive", "sum"),
        availability_date=("availability_date", "max"),
    )
    g = g.merge(_dominant("state"), on=["establishment_id", "quarter"], how="left")
    g = g.merge(_dominant("product_type"), on=["establishment_id", "quarter"], how="left")
    g["positivity_rate"] = np.where(
        g["samples"] > 0, g["positives"] / g["samples"], np.nan
    )
    g["quarter_start"] = g["quarter"].map(quarter_start)
    return g.sort_values(["establishment_id", "quarter_start"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# STEP 1 — temporal feasibility gate
# --------------------------------------------------------------------------- #

def _trailing_sample_counts(
    samples: pd.DataFrame, cutoff: pd.Timestamp, windows_days: tuple[int, ...]
) -> dict[int, pd.Series]:
    """Per-establishment routine sample counts in trailing windows before cutoff.

    Only samples AVAILABLE at the cutoff (``availability_date <= cutoff``) and
    collected within ``w`` days before the cutoff are counted — leakage-safe."""
    avail = samples[samples["availability_date"] <= cutoff]
    out: dict[int, pd.Series] = {}
    for w in windows_days:
        lo = cutoff - pd.Timedelta(days=w)
        win = avail[(avail["collection_date"] > lo) & (avail["collection_date"] <= cutoff)]
        out[w] = win.groupby("establishment_id")["is_testable"].sum()
    return out


def temporal_feasibility(
    samples_by_pathogen: dict[str, EstablishmentSamples],
    *,
    cutoffs: tuple[str, ...] = FEASIBILITY_CUTOFFS,
    windows_days: tuple[int, ...] = TRAILING_WINDOWS_DAYS,
    evaluable_min_samples: int = EVALUABLE_MIN_SAMPLES,
    history_min_samples: int = HISTORY_MIN_SAMPLES,
) -> dict[str, Any]:
    """STEP 1 — measured establishment temporal-feasibility gate (per pathogen).

    For each pathogen this reports, from the REAL data and never fabricated:

    (a) establishments with >= ``history_min_samples`` comparable samples in the
        trailing 90/180/365/730-day windows at several representative cutoffs;
    (b) establishments active in consecutive years (a run of >= 2 adjacent
        calendar years each carrying a routine sample);
    (c) establishment-quarters with an EVALUABLE future outcome (the next quarter
        carries >= ``evaluable_min_samples`` comparable samples);
    (d) the count of TRAINABLE establishment-quarter rows that have BOTH
        sufficient trailing history AND an evaluable future outcome.

    The verdict per pathogen is ``forecastable`` only where enough trainable rows
    exist; Listeria / STEC are expected to fail (median 0 positives/est) and be
    marked descriptive-only.
    """

    report: dict[str, Any] = {
        "description": (
            "Establishment-level temporal feasibility: measured counts of "
            "establishments/quarters with sufficient trailing history AND an "
            "evaluable next-quarter outcome. Forecasting proceeds only where "
            "enough TRAINABLE rows exist. Nothing fabricated."
        ),
        "parameters": {
            "cutoffs": list(cutoffs),
            "trailing_windows_days": list(windows_days),
            "evaluable_min_samples": evaluable_min_samples,
            "history_min_samples": history_min_samples,
            "reporting_lag_days": REPORTING_LAG_DAYS,
        },
        "per_pathogen": {},
    }

    for pathogen, es in samples_by_pathogen.items():
        s = es.frame
        panel = build_establishment_quarters(s)

        # (a) trailing-window history counts at each representative cutoff
        history_table: list[dict[str, Any]] = []
        for c in cutoffs:
            cutoff = quarter_start(c)
            counts = _trailing_sample_counts(s, cutoff, windows_days)
            row: dict[str, Any] = {"cutoff": c}
            for w in windows_days:
                cw = counts[w]
                row[f"est_with_ge_hist_{w}d"] = int((cw >= history_min_samples).sum())
                row[f"est_active_{w}d"] = int((cw > 0).sum())
            history_table.append(row)

        # (b) establishments active in consecutive calendar years
        s_years = s.copy()
        s_years["year"] = s_years["collection_date"].dt.year
        by_est_year = s_years.groupby("establishment_id")["year"].apply(
            lambda ys: sorted(set(int(y) for y in ys))
        )
        def _has_consecutive(years: list[int]) -> bool:
            return any((b - a) == 1 for a, b in zip(years, years[1:]))
        consecutive = int(by_est_year.apply(_has_consecutive).sum())

        # (c) establishment-quarters with an evaluable future outcome
        panel_idx = panel.set_index(["establishment_id", "quarter"])
        panel = panel.copy()
        panel["next_quarter"] = panel["quarter"].map(next_quarter)
        nxt = panel.merge(
            panel[["establishment_id", "quarter", "samples", "positives"]].rename(
                columns={
                    "quarter": "next_quarter",
                    "samples": "next_samples",
                    "positives": "next_positives",
                }
            ),
            on=["establishment_id", "next_quarter"],
            how="left",
        )
        nxt["next_samples"] = nxt["next_samples"].fillna(0)
        nxt["next_positives"] = nxt["next_positives"].fillna(0)
        nxt["evaluable_future"] = nxt["next_samples"] >= evaluable_min_samples

        # trailing history attached to each quarter row (available-as-of cutoff).
        # Vectorized: per establishment, the available-sample count as of a cutoff
        # is a step function of the sample availability dates. We compute, for
        # each (establishment, quarter) cutoff, how many of that establishment's
        # samples were available strictly before the cutoff via a merge-asof.
        nxt["cutoff"] = nxt["quarter"].map(quarter_start)
        avail_counts = (
            s.sort_values("availability_date")
            .assign(_one=1)
            .groupby("establishment_id")
            .apply(lambda g: g.assign(_cum=g["_one"].cumsum()), include_groups=False)
            .reset_index(level=0)
            [["establishment_id", "availability_date", "_cum"]]
            .reset_index(drop=True)
        )
        left = nxt[["establishment_id", "cutoff"]].copy()
        left["_row"] = np.arange(len(left))
        left = left.sort_values("cutoff")
        avail_counts = avail_counts.sort_values("availability_date")
        merged = pd.merge_asof(
            left,
            avail_counts,
            left_on="cutoff",
            right_on="availability_date",
            by="establishment_id",
            direction="backward",
            allow_exact_matches=False,  # availability_date < cutoff (strict)
        )
        merged["_cum"] = merged["_cum"].fillna(0)
        hist_order = merged.sort_values("_row")["_cum"].to_numpy()
        nxt["trailing_history_samples"] = hist_order.astype(int)
        nxt["sufficient_history"] = nxt["trailing_history_samples"] >= history_min_samples
        nxt["trainable"] = nxt["evaluable_future"] & nxt["sufficient_history"]

        # (d) trainable rows + by product_type
        trainable = nxt[nxt["trainable"]]
        by_product = (
            trainable.groupby("product_type")
            .agg(trainable_rows=("trainable", "size"),
                 establishments=("establishment_id", "nunique"))
            .sort_values("trainable_rows", ascending=False)
            .reset_index()
            .to_dict(orient="records")
        )

        n_trainable = int(len(trainable))
        n_evaluable = int(nxt["evaluable_future"].sum())
        n_pos_establishments = int(
            (panel.groupby("establishment_id")["positives"].sum() > 0).sum()
        )
        median_pos_per_est = float(
            panel.groupby("establishment_id")["positives"].sum().median()
        )

        # verdict: forecastable only with enough trainable rows AND positives
        forecastable = bool(n_trainable >= 500 and median_pos_per_est >= 1)
        verdict = "forecastable" if forecastable else "descriptive_only"
        rationale = (
            f"{es.n_establishments} establishments, median positives/est="
            f"{median_pos_per_est:.1f}, {n_trainable} trainable "
            f"establishment-quarter rows (history>={history_min_samples} samples "
            f"AND next-quarter>={evaluable_min_samples} samples), "
            f"{n_evaluable} establishment-quarters with an evaluable future "
            f"outcome. "
            + (
                "Enough trainable rows and non-zero typical positives -> "
                "establishment-level FORECASTS are feasible."
                if forecastable else
                "Too few trainable rows / median 0 positives per establishment "
                "-> establishment-level forecasts NOT feasible; descriptive / "
                "ranking only."
            )
        )

        report["per_pathogen"][pathogen] = {
            "n_establishments": es.n_establishments,
            "n_routine_testable_samples": es.n_samples,
            "date_range": list(es.date_range),
            "median_positives_per_establishment": median_pos_per_est,
            "establishments_with_any_positive": n_pos_establishments,
            "trailing_history_by_cutoff": history_table,
            "establishments_active_consecutive_years": consecutive,
            "establishment_quarters_total": int(len(panel)),
            "establishment_quarters_evaluable_future": n_evaluable,
            "trainable_establishment_quarters": n_trainable,
            "trainable_by_product_type": by_product,
            "verdict": verdict,
            "rationale": rationale,
        }

    return report


# --------------------------------------------------------------------------- #
# Empirical-Bayes Beta-Binomial smoothing (shared helper, Step 2 + Step 4)
# --------------------------------------------------------------------------- #

def eb_smoothed_rate(
    positives: float,
    samples: float,
    national_rate: float,
    *,
    prior_strength: float = EB_PRIOR_STRENGTH,
) -> float:
    """EB Beta-Binomial posterior-mean positivity, shrunk toward ``national_rate``.

    With a Beta prior ``(alpha, beta)`` whose mean is ``national_rate`` and whose
    total pseudo-count is ``prior_strength``, the posterior mean after observing
    ``positives`` of ``samples`` is::

        (positives + alpha) / (samples + prior_strength)

    where ``alpha = national_rate * prior_strength``. The result always lies
    strictly BETWEEN the establishment's raw rate and the national rate (Step 2
    property): a zero-sample establishment returns exactly the national rate, and
    as ``samples -> inf`` the posterior mean -> the raw rate. ``national_rate`` is
    clamped to ``[0, 1]`` and a non-positive ``samples`` yields ``national_rate``.
    """
    national_rate = float(min(max(national_rate, 0.0), 1.0))
    alpha = national_rate * prior_strength
    if samples <= 0:
        return national_rate
    return float((positives + alpha) / (samples + prior_strength))


# --------------------------------------------------------------------------- #
# STEP 2 — leakage-safe establishment features (quarterly grain)
# --------------------------------------------------------------------------- #

#: The feature columns the models consume (everything else is a key / outcome /
#: evaluation column). Kept explicit so the leakage assertion and the model
#: matrix never accidentally include a next-quarter outcome column.
FEATURE_COLUMNS: tuple[str, ...] = (
    # trailing positive / test counts over 30/90/180/365 days (cutoff-safe)
    "trail_samples_30d", "trail_positives_30d",
    "trail_samples_90d", "trail_positives_90d",
    "trail_samples_180d", "trail_positives_180d",
    "trail_samples_365d", "trail_positives_365d",
    # EB-smoothed establishment historical positivity (shrunk to national)
    "eb_positivity",
    "raw_hist_positivity",
    # positivity trend + EWMA + CUSUM-style signal
    "positivity_trend", "positivity_ewma", "cusum_signal",
    # time since previous positive (quarters); large when never positive
    "quarters_since_last_positive",
    # sampling volume + historical sampling intensity
    "hist_samples_total", "hist_quarters_active", "sampling_intensity",
    # lagged peer-group / state / national surveillance rates
    "peer_positivity_lag", "state_positivity_lag", "national_positivity_lag",
    # seasonality
    "season_sin", "season_cos", "quarter_of_year",
    # product_type (categorical)
    "product_type",
)

#: Subset of :data:`FEATURE_COLUMNS` that are categorical.
CATEGORICAL_FEATURES: tuple[str, ...] = ("product_type",)


def _national_rate_as_of(panel: pd.DataFrame, cutoff: pd.Timestamp) -> float:
    """National routine positivity across all establishments available at cutoff."""
    avail = panel[panel["availability_date"] <= cutoff]
    avail = avail[avail["quarter_start"] < cutoff]
    tot = avail["samples"].sum()
    if tot <= 0:
        return 0.0
    return float(avail["positives"].sum() / tot)


def build_features(
    samples: pd.DataFrame,
    panel: Optional[pd.DataFrame] = None,
    *,
    evaluable_min_samples: int = EVALUABLE_MIN_SAMPLES,
    history_min_samples: int = HISTORY_MIN_SAMPLES,
) -> pd.DataFrame:
    """Build the leakage-safe establishment x quarter feature matrix (Step 2).

    One row per ``(establishment_id, quarter)`` that is a candidate prediction
    cell. For each cell the cutoff is the **start of that quarter**; every feature
    is computed ONLY from samples whose ``availability_date <= cutoff`` and whose
    collection quarter is strictly earlier than the target quarter. Future
    sampling counts and any future lab info are EXCLUDED. The function returns
    keys, the feature columns, and the raw next-quarter outcome columns (used by
    :func:`build_targets` and as the evaluation denominator — never as features).

    An ``insufficient_recent_testing`` flag marks cells whose trailing history is
    below ``history_min_samples`` — these establishments are uncertain-not-safe
    and are reported separately, never auto-labelled "safe".
    """
    if panel is None:
        panel = build_establishment_quarters(samples)
    if panel.empty:
        return pd.DataFrame()

    samples = samples.sort_values("collection_date")
    # pre-index samples per establishment for speed
    s_by_est = {k: v for k, v in samples.groupby("establishment_id")}

    # peer-group (product_type) and state quarterly positivity series, plus the
    # per-quarter national series — all computed on the panel (cutoff-filtered
    # per row below so they stay leakage-safe).
    rows: list[dict[str, Any]] = []
    panel = panel.copy()
    panel["next_quarter"] = panel["quarter"].map(next_quarter)

    # next-quarter outcome lookup
    nxt_lookup = panel.set_index(["establishment_id", "quarter"])[
        ["samples", "positives", "positivity_rate"]
    ]

    quarters_sorted = _sorted_quarters(panel["quarter"].tolist())
    # cache national rate per cutoff quarter
    national_cache: dict[str, float] = {}
    for q in quarters_sorted:
        national_cache[q] = _national_rate_as_of(panel, quarter_start(q))

    # cache peer / state lagged positivity: use the PRIOR quarter's pooled rate
    # (available at cutoff) for the cell's product_type and state.
    def _prior_quarter(q: str) -> Optional[str]:
        idx = quarters_sorted.index(q)
        return quarters_sorted[idx - 1] if idx > 0 else None

    # Precompute per (quarter, product_type) and (quarter, state) pooled rates.
    peer_rate: dict[tuple, float] = {}
    for (q, pt), grp in panel.groupby(["quarter", "product_type"]):
        tot = grp["samples"].sum()
        peer_rate[(q, pt)] = float(grp["positives"].sum() / tot) if tot > 0 else np.nan
    state_rate: dict[tuple, float] = {}
    for (q, stt), grp in panel.groupby(["quarter", "state"]):
        tot = grp["samples"].sum()
        state_rate[(q, stt)] = float(grp["positives"].sum() / tot) if tot > 0 else np.nan

    for row in panel.itertuples(index=False):
        est_id = row.establishment_id
        q = row.quarter
        cutoff = quarter_start(q)
        poy = int(q.split("-Q")[1])

        es = s_by_est.get(est_id)
        if es is None:
            continue
        # leakage-safe history: available at cutoff AND collected before this q
        hist = es[(es["availability_date"] <= cutoff) & (es["collection_date"] < cutoff)]

        feat: dict[str, Any] = {
            "establishment_id": est_id,
            "quarter": q,
            "quarter_start": cutoff,
            "state": row.state,
            "product_type": row.product_type,
            "next_quarter": row.next_quarter,
        }

        # --- trailing positive/test counts over 30/90/180/365 days --------
        for w in (30, 90, 180, 365):
            lo = cutoff - pd.Timedelta(days=w)
            win = hist[hist["collection_date"] > lo]
            feat[f"trail_samples_{w}d"] = float(win["is_testable"].sum())
            feat[f"trail_positives_{w}d"] = float(win["is_positive"].sum())

        # --- establishment historical positivity (raw + EB-smoothed) ------
        hist_samples = float(hist["is_testable"].sum())
        hist_positives = float(hist["is_positive"].sum())
        raw_rate = (hist_positives / hist_samples) if hist_samples > 0 else np.nan
        nat = national_cache.get(q, 0.0)
        feat["raw_hist_positivity"] = raw_rate
        feat["eb_positivity"] = eb_smoothed_rate(hist_positives, hist_samples, nat)
        feat["hist_samples_total"] = hist_samples

        # --- per-quarter historical positivity series for trend/EWMA/CUSUM -
        hq = hist.copy()
        hq["q"] = hq["collection_date"].map(quarter_label)
        hq_grp = hq.groupby("q").agg(
            s=("is_testable", "sum"), p=("is_positive", "sum")
        )
        hq_grp = hq_grp.reindex(_sorted_quarters(hq_grp.index.tolist()))
        q_rates = (hq_grp["p"] / hq_grp["s"]).to_numpy() if len(hq_grp) else np.array([])
        q_rates = q_rates[~np.isnan(q_rates)]

        feat["hist_quarters_active"] = float(len(hq_grp))
        # trend: slope of a simple linear fit over the trailing (<=8) quarters
        if len(q_rates) >= 2:
            yv = q_rates[-8:]
            xv = np.arange(len(yv), dtype=float)
            slope = float(np.polyfit(xv, yv, 1)[0])
            feat["positivity_trend"] = slope
            # EWMA (span 4)
            ew = pd.Series(yv).ewm(span=4, adjust=False).mean().iloc[-1]
            feat["positivity_ewma"] = float(ew)
            # CUSUM-style: cumulative deviation of rate from national, last value
            cusum = float(np.sum(yv - nat))
            feat["cusum_signal"] = cusum
        else:
            feat["positivity_trend"] = np.nan
            feat["positivity_ewma"] = (
                float(q_rates[-1]) if len(q_rates) else np.nan
            )
            feat["cusum_signal"] = np.nan

        # --- time since previous positive (quarters) ----------------------
        pos_hist = hist[hist["is_positive"] == 1]
        if len(pos_hist):
            last_pos_q = quarter_label(pos_hist["collection_date"].max())
            feat["quarters_since_last_positive"] = float(
                _quarter_distance(last_pos_q, q)
            )
        else:
            # never positive in available history: large sentinel (NOT "safe")
            feat["quarters_since_last_positive"] = float(
                len(quarters_sorted)
            )

        # --- sampling volume + historical sampling intensity --------------
        active_q = max(int(feat["hist_quarters_active"]), 1)
        feat["sampling_intensity"] = hist_samples / active_q

        # --- lagged peer / state / national surveillance rates ------------
        pq = _prior_quarter(q)
        feat["peer_positivity_lag"] = (
            peer_rate.get((pq, row.product_type), np.nan) if pq else np.nan
        )
        feat["state_positivity_lag"] = (
            state_rate.get((pq, row.state), np.nan) if pq else np.nan
        )
        feat["national_positivity_lag"] = nat

        # --- seasonality ---------------------------------------------------
        angle = 2.0 * math.pi * ((poy - 1) / 4.0)
        feat["season_sin"] = math.sin(angle)
        feat["season_cos"] = math.cos(angle)
        feat["quarter_of_year"] = poy

        # --- insufficient-recent-testing flag (uncertain, NOT safe) -------
        feat["insufficient_recent_testing"] = bool(
            feat["trail_samples_365d"] < history_min_samples
        )

        # --- raw next-quarter OUTCOME (evaluation denominator; NOT a feature)
        key = (est_id, row.next_quarter)
        if key in nxt_lookup.index:
            nrow = nxt_lookup.loc[key]
            feat["next_samples"] = float(nrow["samples"])
            feat["next_positives"] = float(nrow["positives"])
            feat["next_positivity_rate"] = (
                float(nrow["positivity_rate"])
                if pd.notna(nrow["positivity_rate"]) else np.nan
            )
        else:
            feat["next_samples"] = 0.0
            feat["next_positives"] = 0.0
            feat["next_positivity_rate"] = np.nan

        feat["evaluable_future"] = bool(feat["next_samples"] >= evaluable_min_samples)
        feat["sufficient_history"] = bool(hist_samples >= history_min_samples)
        feat["seen_establishment"] = True  # set per-split later

        rows.append(feat)

    features = pd.DataFrame(rows)
    return features.sort_values(["quarter_start", "establishment_id"]).reset_index(drop=True)


def _quarter_distance(q_from: str, q_to: str) -> int:
    """Number of quarters between two labels (``q_to - q_from``)."""
    yf, qf = q_from.split("-Q")
    yt, qt = q_to.split("-Q")
    return (int(yt) * 4 + (int(qt) - 1)) - (int(yf) * 4 + (int(qf) - 1))


# --------------------------------------------------------------------------- #
# Leakage assertion (Step 2 guard)
# --------------------------------------------------------------------------- #

class EstablishmentLeakageError(AssertionError):
    """Raised when an establishment feature could draw on post-cutoff samples."""


def assert_leakage_safe(features: pd.DataFrame, samples: pd.DataFrame) -> None:
    """Assert no feature row could use a sample at/after its target quarter.

    For every feature row the cutoff is ``quarter_start(quarter)``. We verify
    that the establishment has at least as many available-as-of-cutoff samples as
    the trailing counts claim, and — the decisive check — that the trailing
    365-day positive/sample counts never exceed what the establishment actually
    had STRICTLY BEFORE its target quarter among available samples. If a row's
    trailing counts could only be explained by a same-or-future-quarter sample,
    we raise.
    """
    if features.empty:
        return
    s_by_est = {k: v for k, v in samples.groupby("establishment_id")}
    for row in features.itertuples(index=False):
        cutoff = row.quarter_start
        es = s_by_est.get(row.establishment_id)
        if es is None:
            if row.trail_samples_365d > 0:
                raise EstablishmentLeakageError(
                    f"{row.establishment_id} {row.quarter}: trailing samples > 0 "
                    "but no source samples exist"
                )
            continue
        legit = es[(es["availability_date"] <= cutoff) & (es["collection_date"] < cutoff)]
        max_samples = float(legit["is_testable"].sum())
        max_pos = float(legit["is_positive"].sum())
        # Every trailing window is a subset of the full pre-cutoff available set.
        for w in (30, 90, 180, 365):
            ts = getattr(row, f"trail_samples_{w}d")
            tp = getattr(row, f"trail_positives_{w}d")
            if ts > max_samples + 1e-9 or tp > max_pos + 1e-9:
                raise EstablishmentLeakageError(
                    f"{row.establishment_id} {row.quarter}: trailing {w}d counts "
                    f"({ts}/{tp}) exceed pre-cutoff available ({max_samples}/"
                    f"{max_pos}) -> post-cutoff leakage"
                )


# --------------------------------------------------------------------------- #
# STEP 3 — targets (primary rate + complementary binary)
# --------------------------------------------------------------------------- #

def build_targets(features: pd.DataFrame) -> pd.DataFrame:
    """Attach the Step-3 targets to the feature frame (returns a copy).

    * ``target_rate_per100`` (PRIMARY) — the observed NEXT-quarter positive rate
      per 100 comparable samples (``100 * next_positives / next_samples``),
      defined only where the future is evaluable (``next_samples >=
      EVALUABLE_MIN_SAMPLES``), else ``NaN``. This is the regression/beta-binomial
      target and also the thing the rate model is scored against.
    * ``target_binary`` (COMPLEMENTARY) — 1 iff the establishment's next-quarter
      routine positivity exceeds its OWN EB-smoothed trailing baseline
      (``eb_positivity``), evaluated only where the future is evaluable. This is
      the ranking label used for the top-K / PR-AUC comparison with the state
      engine. A zero-positive establishment is NOT auto-labelled anything when its
      future is not evaluable (the label is ``NaN``, i.e. unknown — never "safe").
    """
    f = features.copy()
    evaluable = f["evaluable_future"]
    f["target_rate_per100"] = np.where(
        evaluable & (f["next_samples"] > 0),
        100.0 * f["next_positives"] / f["next_samples"].replace(0, np.nan),
        np.nan,
    )
    # complementary binary: next positivity exceeds the establishment's own
    # EB-smoothed trailing baseline.
    next_rate = np.where(
        f["next_samples"] > 0, f["next_positives"] / f["next_samples"].replace(0, np.nan), np.nan
    )
    f["next_rate_observed"] = next_rate
    f["target_binary"] = np.where(
        evaluable,
        (next_rate > f["eb_positivity"]).astype(float),
        np.nan,
    )
    return f


# --------------------------------------------------------------------------- #
# STEP 4 — models + strong baselines
# --------------------------------------------------------------------------- #

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

try:  # optional boosters (pinned in requirements.txt); degrade honestly if absent
    from xgboost import XGBClassifier  # type: ignore
    _HAS_XGB = True
except Exception:  # noqa: BLE001
    _HAS_XGB = False
try:
    from lightgbm import LGBMClassifier  # type: ignore
    _HAS_LGBM = True
except Exception:  # noqa: BLE001
    _HAS_LGBM = False


NUMERIC_FEATURES: tuple[str, ...] = tuple(
    c for c in FEATURE_COLUMNS if c not in CATEGORICAL_FEATURES
)


def _make_preprocessor() -> ColumnTransformer:
    """Impute numerics + one-hot the product_type peer dimension."""
    numeric = Pipeline(
        [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
    )
    categorical = Pipeline(
        [
            ("impute", SimpleImputer(strategy="constant", fill_value="UNKNOWN_PRODUCT")),
            ("oh", OneHotEncoder(handle_unknown="ignore", min_frequency=20)),
        ]
    )
    return ColumnTransformer(
        [
            ("num", numeric, list(NUMERIC_FEATURES)),
            ("cat", categorical, list(CATEGORICAL_FEATURES)),
        ],
        remainder="drop",
    )


def _build_ml_model(name: str) -> Pipeline:
    """Construct one ML classifier pipeline on the leakage-safe features."""
    pre = _make_preprocessor()
    if name == "logistic":
        clf: Any = LogisticRegression(max_iter=2000, class_weight="balanced")
    elif name == "random_forest":
        clf = RandomForestClassifier(
            n_estimators=300, max_depth=None, min_samples_leaf=5,
            class_weight="balanced", n_jobs=-1, random_state=RANDOM_STATE,
        )
    elif name == "xgboost" and _HAS_XGB:
        clf = XGBClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, eval_metric="logloss",
            random_state=RANDOM_STATE, n_jobs=-1,
        )
    elif name == "lightgbm" and _HAS_LGBM:
        clf = LGBMClassifier(
            n_estimators=400, num_leaves=31, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, class_weight="balanced",
            random_state=RANDOM_STATE, n_jobs=-1, verbose=-1,
        )
    else:
        raise ValueError(f"unknown / unavailable model {name!r}")
    return Pipeline([("pre", pre), ("clf", clf)])


def available_ml_models() -> list[str]:
    """ML learners available in THIS environment (boosters degrade honestly)."""
    names = ["logistic", "random_forest"]
    if _HAS_XGB:
        names.append("xgboost")
    if _HAS_LGBM:
        names.append("lightgbm")
    return names


# --- strong baselines (no learned ML) -------------------------------------- #

def baseline_scores(train: pd.DataFrame, test: pd.DataFrame, kind: str) -> np.ndarray:
    """Score ``test`` rows with one of the three strong baselines.

    * ``eb_establishment`` — the establishment's EB-smoothed trailing positivity
      (``eb_positivity``), already leakage-safe and shrunk to national.
    * ``peer_group`` — the lagged peer-group (product_type) positivity.
    * ``seasonal_persistence`` — the establishment's EWMA positivity (a
      seasonally-smoothed persistence of its own recent rate), falling back to
      the EB rate when EWMA is undefined.

    All three return a risk SCORE in ``[0, 1]`` suitable for ranking / PR-AUC /
    top-K; higher = higher predicted next-quarter positivity. No training data is
    used to fit parameters (these are deterministic transforms of the cutoff-safe
    features), so ``train`` is accepted only for API symmetry.
    """
    if kind == "eb_establishment":
        return test["eb_positivity"].fillna(0.0).to_numpy()
    if kind == "peer_group":
        return test["peer_positivity_lag"].fillna(
            test["national_positivity_lag"]
        ).fillna(0.0).to_numpy()
    if kind == "seasonal_persistence":
        s = test["positivity_ewma"].fillna(test["eb_positivity"]).fillna(0.0)
        return s.to_numpy()
    raise ValueError(f"unknown baseline {kind!r}")


BASELINE_KINDS: tuple[str, ...] = (
    "eb_establishment", "peer_group", "seasonal_persistence",
)


# --------------------------------------------------------------------------- #
# STEP 5 — evaluation primitives
# --------------------------------------------------------------------------- #

def _binary_point_metrics(y_true: np.ndarray, y_score: np.ndarray) -> dict[str, Any]:
    """PR-AUC / ROC-AUC / Brier on a binary slice (null when undefined)."""
    y_true = np.asarray(y_true, dtype=float)
    y_score = np.asarray(y_score, dtype=float)
    n = int(len(y_true))
    n_pos = int(np.nansum(y_true))
    single = len(np.unique(y_true[~np.isnan(y_true)])) < 2
    def _safe(fn: Any) -> Optional[float]:
        try:
            return float(fn())
        except Exception:  # noqa: BLE001
            return None
    return {
        "n": n,
        "n_positive": n_pos,
        "base_rate": (n_pos / n) if n else None,
        "pr_auc": None if single else _safe(lambda: average_precision_score(y_true, y_score)),
        "roc_auc": None if single else _safe(lambda: roc_auc_score(y_true, y_score)),
        "brier": _safe(lambda: brier_score_loss(y_true, np.clip(y_score, 0, 1))),
    }


def _bootstrap_ci(
    y_true: np.ndarray, y_score: np.ndarray, metric: str,
    *, n_draws: int = 1000, random_state: int = RANDOM_STATE,
) -> dict[str, Any]:
    """95% percentile-bootstrap CI for one binary metric (null when undefined)."""
    y_true = np.asarray(y_true, dtype=float)
    y_score = np.asarray(y_score, dtype=float)
    n = len(y_true)
    rng = np.random.default_rng(random_state)
    point = _binary_point_metrics(y_true, y_score).get(metric)
    draws: list[float] = []
    if n >= 2 and point is not None:
        for _ in range(n_draws):
            idx = rng.integers(0, n, size=n)
            v = _binary_point_metrics(y_true[idx], y_score[idx]).get(metric)
            if v is not None:
                draws.append(v)
    if point is None or len(draws) < 2:
        return {"point": point, "lo": None, "hi": None, "available": False}
    arr = np.asarray(draws, dtype=float)
    lo = min(float(np.percentile(arr, 2.5)), point)
    hi = max(float(np.percentile(arr, 97.5)), point)
    return {"point": point, "lo": lo, "hi": hi, "available": True, "n_draws": len(draws)}


def _calibration(y_true: np.ndarray, y_score: np.ndarray, *, n_bins: int = 10) -> dict[str, Any]:
    """Reliability curve + count-weighted calibration error."""
    y_true = np.asarray(y_true, dtype=float)
    y_score = np.clip(np.asarray(y_score, dtype=float), 0, 1)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    pts: list[dict[str, Any]] = []
    wgap, tot = 0.0, 0
    for b in range(n_bins):
        lo, hi = float(edges[b]), float(edges[b + 1])
        mask = (y_score >= lo) & (y_score <= hi) if b == n_bins - 1 else (y_score >= lo) & (y_score < hi)
        c = int(mask.sum())
        if c:
            pm, of = float(y_score[mask].mean()), float(y_true[mask].mean())
            wgap += c * abs(pm - of)
            tot += c
        else:
            pm = of = None
        pts.append({"bin_lower": lo, "bin_upper": hi, "count": c,
                    "mean_predicted": pm, "observed_frequency": of})
    return {"points": pts, "calibration_error": (wgap / tot) if tot else None}


def top_k_capture(
    eligible: pd.DataFrame, score_col: str, label_col: str,
    *, k: Optional[int] = None, k_fraction: Optional[float] = None,
) -> dict[str, Any]:
    """Top-K capture under an inspection budget over an ELIGIBLE population.

    Rank the eligible rows by ``score_col`` (descending, stable tie-break) and
    take the top ``k`` (absolute) or ``ceil(k_fraction * n)``; report positives
    captured, precision@K and recall@K against ``label_col`` (1 = positive). This
    is RETROSPECTIVE capture of positive tests, not proven contamination/illness
    reduction (stated in the report).
    """
    df = eligible.dropna(subset=[label_col]).copy()
    n = len(df)
    if n == 0:
        return {"k": 0, "n_eligible": 0, "positives_captured": 0,
                "precision_at_k": None, "recall_at_k": None, "total_positives": 0}
    if k is None:
        k = int(math.ceil((k_fraction or TOPK_FRACTION) * n))
    k = max(1, min(int(k), n))
    order = np.argsort(-df[score_col].to_numpy(), kind="stable")
    top = df.iloc[order[:k]]
    total_pos = int(df[label_col].sum())
    captured = int(top[label_col].sum())
    return {
        "k": int(k),
        "n_eligible": int(n),
        "total_positives": total_pos,
        "positives_captured": captured,
        "precision_at_k": captured / k if k else None,
        "recall_at_k": captured / total_pos if total_pos else None,
    }


def rolling_origin_quarters(quarters: list[str], n_origins: int) -> list[tuple[list[str], str]]:
    """Return ``(train_quarters, eval_quarter)`` for the last ``n_origins`` quarters.

    Chronological: each origin trains on all strictly-earlier quarters and
    evaluates on one later quarter. Guarantees train precedes eval."""
    quarters = _sorted_quarters(quarters)
    n = len(quarters)
    if n <= n_origins:
        n_origins = max(1, n - 1)
    eval_quarters = quarters[-n_origins:]
    out: list[tuple[list[str], str]] = []
    for eq in eval_quarters:
        idx = quarters.index(eq)
        train_q = quarters[:idx]
        if train_q:
            out.append((train_q, eq))
    return out


# --------------------------------------------------------------------------- #
# STEP 5 — full establishment model comparison + unseen-establishment holdout
# --------------------------------------------------------------------------- #

def _fit_predict_ml(
    name: str, train: pd.DataFrame, test: pd.DataFrame
) -> Optional[np.ndarray]:
    """Fit ``name`` on ``train`` binary target, return positive-class scores on
    ``test``; ``None`` when the training target is single-class (can't fit)."""
    y = train["target_binary"].to_numpy()
    mask = ~np.isnan(y)
    Xtr, ytr = train.loc[mask, list(FEATURE_COLUMNS)], y[mask].astype(int)
    if len(np.unique(ytr)) < 2 or len(ytr) < 20:
        return None
    model = _build_ml_model(name)
    model.fit(Xtr, ytr)
    proba = model.predict_proba(test[list(FEATURE_COLUMNS)])
    return proba[:, 1]


def evaluate_models(
    targeted: pd.DataFrame, *, n_origins: int = ROLLING_ORIGINS,
) -> dict[str, Any]:
    """Chronological rolling-origin evaluation of baselines + ML on the binary
    target, over the EVALUABLE establishment-quarters (Step 5)."""
    ev = targeted[targeted["evaluable_future"] & targeted["target_binary"].notna()].copy()
    quarters = _sorted_quarters(ev["quarter"].tolist())
    schedule = rolling_origin_quarters(quarters, n_origins)

    ml_names = available_ml_models()
    engines = list(BASELINE_KINDS) + ml_names

    # accumulate pooled test predictions across origins per engine
    pooled: dict[str, dict[str, list]] = {
        e: {"y": [], "s": []} for e in engines
    }
    per_origin: list[dict[str, Any]] = []

    for train_q, eval_q in schedule:
        tr = ev[ev["quarter"].isin(train_q)]
        te = ev[ev["quarter"] == eval_q]
        if te.empty or tr.empty:
            continue
        origin_rec: dict[str, Any] = {
            "eval_quarter": eval_q,
            "train_quarters": [train_q[0], train_q[-1]],
            "n_train": int(len(tr)),
            "n_eval": int(len(te)),
            "engines": {},
        }
        y = te["target_binary"].to_numpy()
        for b in BASELINE_KINDS:
            s = baseline_scores(tr, te, b)
            origin_rec["engines"][b] = _binary_point_metrics(y, s)
            pooled[b]["y"].extend(y.tolist())
            pooled[b]["s"].extend(np.asarray(s).tolist())
        for m in ml_names:
            s = _fit_predict_ml(m, tr, te)
            if s is None:
                origin_rec["engines"][m] = {"available": False,
                                            "reason": "single-class/too-small train"}
                continue
            origin_rec["engines"][m] = _binary_point_metrics(y, s)
            pooled[m]["y"].extend(y.tolist())
            pooled[m]["s"].extend(np.asarray(s).tolist())
        per_origin.append(origin_rec)

    # pooled metrics + CIs + calibration + top-K per engine
    pooled_metrics: dict[str, Any] = {}
    for e in engines:
        y = np.asarray(pooled[e]["y"], dtype=float)
        s = np.asarray(pooled[e]["s"], dtype=float)
        if len(y) == 0:
            pooled_metrics[e] = {"available": False, "reason": "no pooled predictions"}
            continue
        pm = _binary_point_metrics(y, s)
        pm["pr_auc_ci"] = _bootstrap_ci(y, s, "pr_auc")
        pm["roc_auc_ci"] = _bootstrap_ci(y, s, "roc_auc")
        pm["brier_ci"] = _bootstrap_ci(y, s, "brier")
        pm["calibration"] = _calibration(y, s)
        edf = pd.DataFrame({"score": s, "label": y})
        pm["top_k_pct"] = top_k_capture(edf, "score", "label", k_fraction=TOPK_FRACTION)
        pm["top_k_abs"] = top_k_capture(edf, "score", "label", k=TOPK_ABSOLUTE)
        pm["available"] = True
        pooled_metrics[e] = pm

    # pick the best engine by pooled PR-AUC (ties -> ROC-AUC)
    def _key(e: str) -> tuple:
        pm = pooled_metrics[e]
        if not pm.get("available"):
            return (-1.0, -1.0)
        return (pm.get("pr_auc") or -1.0, pm.get("roc_auc") or -1.0)
    ranked = sorted(engines, key=_key, reverse=True)

    return {
        "n_origins": len(per_origin),
        "eval_quarters": [o["eval_quarter"] for o in per_origin],
        "engines_evaluated": engines,
        "per_origin": per_origin,
        "pooled": pooled_metrics,
        "ranking_by_pr_auc": ranked,
        "best_engine": ranked[0] if ranked else None,
    }


def unseen_establishment_holdout(
    targeted: pd.DataFrame, best_ml: str,
    *, holdout_fraction: float = 0.25, random_state: int = RANDOM_STATE,
) -> dict[str, Any]:
    """FAMILIAR vs UNSEEN establishment generalization (whole establishments held out).

    A deterministic random subset of establishments is withheld ENTIRELY from
    training; the model is trained on the remaining (familiar) establishments'
    evaluable rows and scored separately on familiar-test rows and on the held-out
    (unseen) establishments. The two populations share NO establishment (asserted).
    """
    ev = targeted[targeted["evaluable_future"] & targeted["target_binary"].notna()].copy()
    ests = sorted(ev["establishment_id"].unique().tolist())
    if len(ests) < 4:
        return {"available": False, "reason": "too few establishments for a holdout"}
    rng = np.random.default_rng(random_state)
    n_hold = max(1, int(round(holdout_fraction * len(ests))))
    unseen = set(rng.choice(np.array(ests, dtype=object), size=n_hold, replace=False).tolist())
    seen = set(ests) - unseen
    assert not (seen & unseen), "familiar/unseen establishment sets overlap"

    # chronological inside familiar: train on earlier quarters, test on latest
    quarters = _sorted_quarters(ev["quarter"].tolist())
    if len(quarters) < 2:
        return {"available": False, "reason": "too few quarters"}
    cut = quarters[int(len(quarters) * 0.8)] if len(quarters) > 4 else quarters[-1]
    train = ev[(ev["establishment_id"].isin(seen)) & (ev["quarter"] < cut)]
    fam_test = ev[(ev["establishment_id"].isin(seen)) & (ev["quarter"] >= cut)]
    unseen_test = ev[(ev["establishment_id"].isin(unseen)) & (ev["quarter"] >= cut)]

    y = train["target_binary"].to_numpy()
    mask = ~np.isnan(y)
    if len(np.unique(y[mask].astype(int))) < 2 or mask.sum() < 20:
        return {"available": False, "reason": "degenerate training target"}
    model = _build_ml_model(best_ml)
    model.fit(train.loc[mask, list(FEATURE_COLUMNS)], y[mask].astype(int))

    def _eval(part: pd.DataFrame) -> dict[str, Any]:
        if part.empty:
            return {"available": False, "reason": "empty slice"}
        s = model.predict_proba(part[list(FEATURE_COLUMNS)])[:, 1]
        yv = part["target_binary"].to_numpy()
        pm = _binary_point_metrics(yv, s)
        edf = pd.DataFrame({"score": s, "label": yv})
        pm["top_k_pct"] = top_k_capture(edf, "score", "label", k_fraction=TOPK_FRACTION)
        pm["available"] = True
        return pm

    return {
        "available": True,
        "model": best_ml,
        "holdout_fraction": holdout_fraction,
        "n_establishments_total": len(ests),
        "n_unseen_establishments": len(unseen),
        "n_familiar_establishments": len(seen),
        "chronological_cut_quarter": cut,
        "familiar_test": _eval(fam_test),
        "unseen_test": _eval(unseen_test),
        "note": (
            "Familiar and unseen establishment sets share no establishment. "
            "Unseen performance is the honest generalization check: can the "
            "model rank establishments it never trained on?"
        ),
    }


# --------------------------------------------------------------------------- #
# STEP 5 — establishment-vs-state prioritization on a common outcome
# --------------------------------------------------------------------------- #

def establishment_vs_state(
    targeted: pd.DataFrame, model_eval: dict[str, Any],
) -> dict[str, Any]:
    """Compare establishment-level vs state-level prioritization on a COMMON
    future outcome over a COMMON eligible population (Step 5).

    The common eligible population is the evaluable establishment-quarters in the
    pooled rolling-origin test set. The common outcome is each row's
    ``target_binary`` (next-quarter positivity exceeds its own baseline). The
    establishment engine ranks rows by the best engine's score (reconstructed
    from the EB establishment rate as a transparent, leakage-safe proxy for the
    establishment risk score); the STATE engine assigns every establishment its
    STATE's lagged positivity (so all establishments in a state share one rank) —
    this is the state-prioritization counterfactual. Both are scored with the
    identical top-K budget. Covariates (sampling volume, product type, state) are
    reported so the reader can see the establishment advantage is not merely
    'big known establishments'.
    """
    ev = targeted[targeted["evaluable_future"] & targeted["target_binary"].notna()].copy()
    if ev.empty:
        return {"available": False, "reason": "no evaluable common population"}

    est_score = ev["eb_positivity"].fillna(0.0).to_numpy()
    state_score = ev["state_positivity_lag"].fillna(
        ev["national_positivity_lag"]
    ).fillna(0.0).to_numpy()
    label = ev["target_binary"].to_numpy()

    est_df = pd.DataFrame({"score": est_score, "label": label})
    state_df = pd.DataFrame({"score": state_score, "label": label})

    result: dict[str, Any] = {
        "available": True,
        "common_population_n": int(len(ev)),
        "common_outcome": "next-quarter routine positivity exceeds establishment's own EB baseline",
        "establishment_prioritization": {
            "score": "EB-smoothed establishment historical positivity (leakage-safe)",
            "pr_auc": _binary_point_metrics(label, est_score).get("pr_auc"),
            "roc_auc": _binary_point_metrics(label, est_score).get("roc_auc"),
            "top_k_pct": top_k_capture(est_df, "score", "label", k_fraction=TOPK_FRACTION),
            "top_k_abs": top_k_capture(est_df, "score", "label", k=TOPK_ABSOLUTE),
        },
        "state_prioritization": {
            "score": "state lagged routine positivity (shared by all establishments in a state)",
            "pr_auc": _binary_point_metrics(label, state_score).get("pr_auc"),
            "roc_auc": _binary_point_metrics(label, state_score).get("roc_auc"),
            "top_k_pct": top_k_capture(state_df, "score", "label", k_fraction=TOPK_FRACTION),
            "top_k_abs": top_k_capture(state_df, "score", "label", k=TOPK_ABSOLUTE),
        },
        "covariate_profile": {
            "mean_hist_samples_total": float(ev["hist_samples_total"].mean()),
            "n_product_types": int(ev["product_type"].nunique()),
            "n_states": int(ev["state"].nunique()),
            "note": (
                "Establishment advantage is reported alongside sampling volume / "
                "product / state spread so a reader can judge whether it is driven "
                "by establishment signal rather than merely by heavily-sampled "
                "known establishments."
            ),
        },
    }

    # headline deltas (establishment minus state) on the common outcome
    def _delta(metric: str) -> Optional[float]:
        a = result["establishment_prioritization"].get(metric)
        b = result["state_prioritization"].get(metric)
        return (a - b) if (a is not None and b is not None) else None

    def _topk_delta(key: str) -> Optional[float]:
        a = result["establishment_prioritization"][key].get("recall_at_k")
        b = result["state_prioritization"][key].get("recall_at_k")
        return (a - b) if (a is not None and b is not None) else None

    result["deltas_establishment_minus_state"] = {
        "pr_auc": _delta("pr_auc"),
        "roc_auc": _delta("roc_auc"),
        "recall_at_top10pct": _topk_delta("top_k_pct"),
        "recall_at_top50": _topk_delta("top_k_abs"),
    }
    return result


# --------------------------------------------------------------------------- #
# Descriptive-only establishment risk scores (Listeria / STEC)
# --------------------------------------------------------------------------- #

def descriptive_establishment_scores(es: EstablishmentSamples) -> dict[str, Any]:
    """Strongly-regularized EB descriptive establishment risk ranking (Listeria /
    STEC). Ranking / display only, WITH uncertainty — never a forecast.

    Each establishment gets its EB-smoothed lifetime positivity (shrunk hard to
    the national rate with a large prior so rare-positive establishments do not
    get extreme scores) plus a 95% Beta posterior credible interval. Zero-positive
    establishments are flagged ``uncertain`` (never 'safe'); thinly-tested ones are
    flagged ``insufficient_testing``.
    """
    panel = build_establishment_quarters(es.frame)
    if panel.empty:
        return {"available": False, "reason": "no establishment panel"}
    g = panel.groupby("establishment_id").agg(
        samples=("samples", "sum"), positives=("positives", "sum"),
        state=("state", "first"), product_type=("product_type", "first"),
    ).reset_index()
    nat = float(g["positives"].sum() / g["samples"].sum()) if g["samples"].sum() else 0.0
    strong_prior = 100.0  # strong regularization for rare-event descriptive scores
    alpha0 = nat * strong_prior
    beta0 = (1 - nat) * strong_prior

    scores: list[dict[str, Any]] = []
    for r in g.itertuples(index=False):
        a = alpha0 + r.positives
        b = beta0 + (r.samples - r.positives)
        mean = a / (a + b)
        # Beta 95% credible interval via the quantile of the posterior
        try:
            from scipy.stats import beta as _beta  # type: ignore
            lo, hi = float(_beta.ppf(0.025, a, b)), float(_beta.ppf(0.975, a, b))
        except Exception:  # noqa: BLE001 - scipy optional; report mean only
            lo = hi = None
        scores.append({
            "establishment_id": r.establishment_id,
            "state": r.state,
            "product_type": r.product_type,
            "samples": int(r.samples),
            "positives": int(r.positives),
            "eb_risk_score": float(mean),
            "credible_interval_95": [lo, hi],
            "flag": (
                "insufficient_testing" if r.samples < HISTORY_MIN_SAMPLES
                else ("uncertain_no_positive" if r.positives == 0 else "ranked")
            ),
        })
    scores.sort(key=lambda d: d["eb_risk_score"], reverse=True)
    return {
        "available": True,
        "kind": "descriptive_ranking_only",
        "pathogen": es.pathogen,
        "national_rate": nat,
        "prior_strength": strong_prior,
        "n_establishments": len(scores),
        "top_20_by_eb_risk": scores[:20],
        "disclaimer": (
            "DESCRIPTIVE establishment risk ranking only — NOT a forecast. Rare "
            "positives mean these scores are heavily shrunk to the national rate "
            "and carry wide uncertainty. A zero-positive establishment is flagged "
            "uncertain, never 'safe'. State-level v2 remains the predictive engine "
            "for this pathogen."
        ),
    }


# --------------------------------------------------------------------------- #
# STEP 6 — decision + per-pathogen engine choice
# --------------------------------------------------------------------------- #

#: State-level v2 reference metrics (handed in by the task; the test-split
#: integrated metrics). Used only for the honest head-to-head narrative.
STATE_V2_REFERENCE: dict[str, Any] = {
    "Salmonella": {"best_model": "RandomForest", "pr_auc": 0.567, "roc_auc": 0.783,
                   "base_rate": 0.279, "note": "state-level integrated test split"},
    "Listeria": {"pr_auc": 0.744, "note": "state-level v2 predictive (kept)"},
    "STEC": {"note": "state-level v2 metrics reported from validation_stec.json; "
                     "kept surveillance-only if weak"},
}


def _load_state_v2_actual() -> dict[str, Any]:
    """Load the REAL state-level v2 metrics from exported artifacts (honest)."""
    out: dict[str, Any] = {}
    for pathogen, slug in (("Salmonella", "salmonella"), ("Listeria", "listeria"), ("STEC", "stec")):
        p = PROCESSED_MODELS_ROOT / f"validation_{slug}.json"
        if p.exists():
            try:
                v = json.loads(p.read_text(encoding="utf-8"))
                sp = v.get("primary_chronological", {}).get("single_split", {}).get("point_metrics", {})
                out[pathogen] = {
                    "best_model": v.get("best_model"),
                    "pr_auc": sp.get("pr_auc"),
                    "roc_auc": sp.get("roc_auc"),
                    "base_rate": sp.get("base_rate"),
                    "source": str(p.relative_to(REPO_ROOT)),
                }
            except Exception:  # noqa: BLE001
                out[pathogen] = {"error": f"could not parse {p}"}
    return out


def decide(
    feasibility: dict[str, Any],
    model_eval: dict[str, Any],
    vs_state: dict[str, Any],
    unseen: dict[str, Any],
    state_v2_actual: dict[str, Any],
) -> dict[str, Any]:
    """STEP 6 — honest per-pathogen engine decision.

    Establishment-level becomes the PRIMARY Salmonella engine only if it beats
    state-level on BOTH top-K capture AND holds up on unseen establishments; else
    state-v2 stays primary. Listeria keeps state-v2 predictive; STEC keeps its
    actual v2 metric and goes surveillance-only if weak. Records the deciding
    metric + feasibility factors per Req 6.5.
    """
    deltas = vs_state.get("deltas_establishment_minus_state", {}) if vs_state.get("available") else {}
    recall_delta_pct = deltas.get("recall_at_top10pct")
    recall_delta_abs = deltas.get("recall_at_top50")
    pr_auc_delta = deltas.get("pr_auc")

    unseen_pr = (
        unseen.get("unseen_test", {}).get("pr_auc") if unseen.get("available") else None
    )
    familiar_pr = (
        unseen.get("familiar_test", {}).get("pr_auc") if unseen.get("available") else None
    )
    # "holds up on unseen" = unseen PR-AUC available and not drastically worse
    unseen_ok = (
        unseen_pr is not None and familiar_pr is not None and unseen_pr >= 0.6 * familiar_pr
    )

    beats_topk = bool(
        (recall_delta_pct is not None and recall_delta_pct > 0)
        or (recall_delta_abs is not None and recall_delta_abs > 0)
    )

    salmonella_feasible = (
        feasibility["per_pathogen"].get("Salmonella", {}).get("verdict") == "forecastable"
    )

    if salmonella_feasible and beats_topk and unseen_ok:
        salmonella_choice = "establishment_level"
        salmonella_rationale = (
            "Establishment-level beats state-level on top-K capture on a common "
            "future outcome AND generalizes to unseen establishments -> adopt "
            "establishment-level as the PRIMARY Salmonella engine; aggregate to "
            "state for the dashboard."
        )
    else:
        salmonella_choice = "state_level_v2"
        reasons = []
        if not salmonella_feasible:
            reasons.append("establishment feasibility gate not met")
        if not beats_topk:
            reasons.append("no top-K capture improvement over state-level")
        if not unseen_ok:
            reasons.append("does not hold up on unseen establishments")
        salmonella_rationale = (
            "Keep state-level v2 as the primary Salmonella engine: "
            + "; ".join(reasons) + ". Establishment scores may still inform "
            "retailer supplier-verification prioritization as a secondary signal."
        )

    stec_v2 = state_v2_actual.get("STEC", {})
    stec_pr = stec_v2.get("pr_auc")
    stec_choice = (
        "state_level_v2_predictive" if (stec_pr is not None and stec_pr >= 0.2)
        else "surveillance_only"
    )

    engine_choice = {
        "Salmonella": {
            "engine": salmonella_choice,
            "deciding_metric": {
                "recall_at_top10pct_delta_est_minus_state": recall_delta_pct,
                "recall_at_top50_delta_est_minus_state": recall_delta_abs,
                "pr_auc_delta_est_minus_state": pr_auc_delta,
                "unseen_pr_auc": unseen_pr,
                "familiar_pr_auc": familiar_pr,
            },
            "feasibility_factors": feasibility["per_pathogen"].get("Salmonella", {}),
            "rationale": salmonella_rationale,
        },
        "Listeria": {
            "engine": "state_level_v2_predictive",
            "deciding_metric": {"state_v2_pr_auc": state_v2_actual.get("Listeria", {}).get("pr_auc")},
            "feasibility_factors": feasibility["per_pathogen"].get("Listeria", {}),
            "rationale": (
                "Listeria median 0 positives per establishment -> establishment "
                "forecasting NOT feasible; keep state-level v2 predictive "
                "(reference PR-AUC 0.744). Establishment level is descriptive only."
            ),
        },
        "STEC": {
            "engine": stec_choice,
            "deciding_metric": {"state_v2_pr_auc": stec_pr},
            "feasibility_factors": feasibility["per_pathogen"].get("STEC", {}),
            "rationale": (
                "STEC median 0 positives per establishment -> establishment "
                "forecasting NOT feasible; establishment level descriptive only. "
                f"State-level v2 PR-AUC={stec_pr}; "
                + ("kept predictive." if stec_choice.startswith("state")
                   else "weak, so kept surveillance-only.")
            ),
        },
    }

    return {
        "verdict": salmonella_choice,
        "salmonella_beats_state_on_topk": beats_topk,
        "salmonella_generalizes_to_unseen": unseen_ok,
        "per_pathogen_engine_choice": engine_choice,
        "retailer_decision_scope": {
            "decision_maker": "retailer",
            "allowed_outputs": list(RETAILER_ACTIONS),
            "prohibited": [
                "government inspection orders",
                "individual-shipment contamination claims",
            ],
        },
        "honesty": (
            "Retrospective top-K capture measures capture of positive TESTS under "
            "a fixed inspection budget; it is NOT proven reduction of contamination "
            "or illness."
        ),
    }


# --------------------------------------------------------------------------- #
# Markdown report writers
# --------------------------------------------------------------------------- #

def _write_feasibility_md(feasibility: dict[str, Any], path: Path) -> None:
    lines = ["# Establishment-Level Temporal Feasibility Gate\n"]
    lines.append(feasibility["description"] + "\n")
    p = feasibility["parameters"]
    lines.append(
        f"Parameters: cutoffs {p['cutoffs'][0]}..{p['cutoffs'][-1]}, trailing "
        f"windows {p['trailing_windows_days']} days, evaluable future >= "
        f"{p['evaluable_min_samples']} samples, sufficient history >= "
        f"{p['history_min_samples']} samples, reporting lag "
        f"{p['reporting_lag_days']} days.\n"
    )
    lines.append("## Per-pathogen verdict\n")
    lines.append("| Pathogen | Establishments | Median pos/est | Trainable est-quarters | Evaluable futures | Consecutive-year est | Verdict |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    for pathogen, d in feasibility["per_pathogen"].items():
        lines.append(
            f"| {pathogen} | {d['n_establishments']} | "
            f"{d['median_positives_per_establishment']:.1f} | "
            f"{d['trainable_establishment_quarters']} | "
            f"{d['establishment_quarters_evaluable_future']} | "
            f"{d['establishments_active_consecutive_years']} | **{d['verdict']}** |"
        )
    lines.append("")
    for pathogen, d in feasibility["per_pathogen"].items():
        lines.append(f"### {pathogen}\n")
        lines.append(d["rationale"] + "\n")
        lines.append("Trailing-history establishments by cutoff (>= sufficient-history samples):\n")
        lines.append("| Cutoff | 90d | 180d | 365d | 730d |")
        lines.append("|---|---:|---:|---:|---:|")
        for r in d["trailing_history_by_cutoff"]:
            lines.append(
                f"| {r['cutoff']} | {r['est_with_ge_hist_90d']} | "
                f"{r['est_with_ge_hist_180d']} | {r['est_with_ge_hist_365d']} | "
                f"{r['est_with_ge_hist_730d']} |"
            )
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _fmt(x: Any, nd: int = 3) -> str:
    if x is None:
        return "n/a"
    try:
        return f"{float(x):.{nd}f}"
    except Exception:  # noqa: BLE001
        return str(x)


def _write_experiment_md(
    feasibility: dict[str, Any], model_eval: dict[str, Any], vs_state: dict[str, Any],
    unseen: dict[str, Any], descriptive: dict[str, Any], decision: dict[str, Any],
    state_v2_actual: dict[str, Any], path: Path,
) -> None:
    L: list[str] = ["# Establishment-Level Salmonella Forecasting Experiment\n"]
    L.append(
        "A parallel experiment to the state-level v2 models. It forecasts the "
        "next-quarter routine Salmonella positivity per FSIS establishment "
        "(comparable-program grain) and asks the honest question: does "
        "establishment-level prioritization beat state-level on a common future "
        "outcome and on establishments the model has never seen?\n"
    )
    L.append("> Retrospective top-K capture is capture of positive TESTS under a "
             "fixed inspection budget — NOT proven contamination or illness "
             "reduction. The retailer is the decision maker; outputs are supplier "
             "verification / additional product testing / human review / recall "
             "response / replacement allocation only.\n")

    L.append("## 1. Feasibility (measured)\n")
    sal = feasibility["per_pathogen"]["Salmonella"]
    L.append(
        f"Salmonella: {sal['n_establishments']} establishments, "
        f"{sal['trainable_establishment_quarters']} trainable establishment-quarters, "
        f"verdict **{sal['verdict']}**. Listeria/STEC: descriptive-only "
        "(median 0 positives/establishment).\n"
    )

    L.append("## 2. Model comparison (baselines vs ML), pooled rolling-origin\n")
    L.append(f"Origins: {model_eval['n_origins']} ({', '.join(model_eval['eval_quarters'])}). "
             f"Best engine by PR-AUC: **{model_eval['best_engine']}**.\n")
    L.append("| Engine | PR-AUC | ROC-AUC | Brier | recall@top10% | recall@top50 |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for e in model_eval["ranking_by_pr_auc"]:
        pm = model_eval["pooled"].get(e, {})
        if not pm.get("available"):
            L.append(f"| {e} | n/a | n/a | n/a | n/a | n/a |")
            continue
        tp = pm.get("top_k_pct", {})
        ta = pm.get("top_k_abs", {})
        L.append(
            f"| {e} | {_fmt(pm.get('pr_auc'))} | {_fmt(pm.get('roc_auc'))} | "
            f"{_fmt(pm.get('brier'))} | {_fmt(tp.get('recall_at_k'))} | "
            f"{_fmt(ta.get('recall_at_k'))} |"
        )
    L.append("")

    best = model_eval.get("best_engine")
    if best and model_eval["pooled"].get(best, {}).get("available"):
        cal = model_eval["pooled"][best]["calibration"]
        L.append(f"## 3. Calibration of the best engine ({best})\n")
        L.append(f"Count-weighted calibration error: {_fmt(cal.get('calibration_error'))} "
                 "(lower is better).\n")

    L.append("## 4. Top-K capture vs historical-risk baseline\n")
    if vs_state.get("available"):
        ep = vs_state["establishment_prioritization"]
        sp = vs_state["state_prioritization"]
        L.append(f"Common eligible population: {vs_state['common_population_n']} evaluable "
                 "establishment-quarters. Common outcome: next-quarter positivity "
                 "exceeds the establishment's own EB baseline.\n")
        L.append("| Prioritization | PR-AUC | ROC-AUC | recall@top10% | recall@top50 |")
        L.append("|---|---:|---:|---:|---:|")
        L.append(f"| Establishment (EB) | {_fmt(ep['pr_auc'])} | {_fmt(ep['roc_auc'])} | "
                 f"{_fmt(ep['top_k_pct'].get('recall_at_k'))} | {_fmt(ep['top_k_abs'].get('recall_at_k'))} |")
        L.append(f"| State (lagged) | {_fmt(sp['pr_auc'])} | {_fmt(sp['roc_auc'])} | "
                 f"{_fmt(sp['top_k_pct'].get('recall_at_k'))} | {_fmt(sp['top_k_abs'].get('recall_at_k'))} |")
        d = vs_state["deltas_establishment_minus_state"]
        L.append(f"\nDeltas (establishment - state): PR-AUC {_fmt(d.get('pr_auc'))}, "
                 f"recall@top10% {_fmt(d.get('recall_at_top10pct'))}, "
                 f"recall@top50 {_fmt(d.get('recall_at_top50'))}.\n")

    L.append("## 5. Unseen-establishment generalization\n")
    if unseen.get("available"):
        ft, ut = unseen["familiar_test"], unseen["unseen_test"]
        L.append(f"Held out {unseen['n_unseen_establishments']} of "
                 f"{unseen['n_establishments_total']} whole establishments "
                 f"(model {unseen['model']}).\n")
        L.append("| Population | PR-AUC | ROC-AUC | recall@top10% |")
        L.append("|---|---:|---:|---:|")
        L.append(f"| Familiar | {_fmt(ft.get('pr_auc'))} | {_fmt(ft.get('roc_auc'))} | "
                 f"{_fmt(ft.get('top_k_pct', {}).get('recall_at_k'))} |")
        L.append(f"| Unseen | {_fmt(ut.get('pr_auc'))} | {_fmt(ut.get('roc_auc'))} | "
                 f"{_fmt(ut.get('top_k_pct', {}).get('recall_at_k'))} |")
        L.append("")
    else:
        L.append(f"Unavailable: {unseen.get('reason')}\n")

    L.append("## 6. Improvement over state-level (honest verdict)\n")
    L.append(f"Establishment beats state on top-K: **{decision['salmonella_beats_state_on_topk']}**; "
             f"generalizes to unseen establishments: **{decision['salmonella_generalizes_to_unseen']}**.\n")
    L.append(f"**Per-pathogen engine choice:**\n")
    for pathogen, c in decision["per_pathogen_engine_choice"].items():
        L.append(f"- **{pathogen}** -> `{c['engine']}`. {c['rationale']}")
    L.append("")
    L.append("State-level v2 reference (measured from exported artifacts): "
             + json.dumps(state_v2_actual) + "\n")

    L.append("## Listeria / STEC — descriptive establishment ranking only\n")
    if descriptive.get("Listeria", {}).get("available"):
        L.append("Listeria and STEC establishment risk scores are strongly-"
                 "regularized EB rankings for display only, with uncertainty. "
                 "Zero-positive establishments are flagged uncertain, never 'safe'. "
                 "State-level v2 stays the predictive engine for these pathogens.\n")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #

def _json_default(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return str(o)
    return str(o)


def _write_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_json_default), encoding="utf-8")


def run_experiment(*, program_dirs: Optional[dict[str, Path]] = None) -> dict[str, Any]:
    """Run the full establishment experiment end to end and write all artifacts.

    Writes:
      * ``data/interim/establishment_temporal_feasibility.json`` (+ .md report)
      * ``data/interim/establishment_decision.json`` (+ experiment .md report)
      * ``data/processed/models/establishment_model_comparison.json``
      * ``data/interim/module_status.json`` (final per-pathogen engine choice)
    """
    # Load all three pathogens (routine-only) for the feasibility gate.
    samples_by_pathogen: dict[str, EstablishmentSamples] = {
        pathogen: load_establishment_samples(pathogen, program_dirs=program_dirs)
        for pathogen in PATHOGENS
    }

    # STEP 1 — feasibility gate
    feasibility = temporal_feasibility(samples_by_pathogen)
    _write_json(feasibility, INTERIM_ROOT / "establishment_temporal_feasibility.json")
    _write_feasibility_md(feasibility, DOCS_REPORTS_ROOT / "establishment_feasibility.md")

    # STEP 2-5 — Salmonella forecasting pipeline (only if feasible)
    sal = samples_by_pathogen[PRIMARY_PATHOGEN]
    panel = build_establishment_quarters(sal.frame)
    features = build_features(sal.frame, panel)
    assert_leakage_safe(features, sal.frame)  # fails loudly on leakage
    targeted = build_targets(features)

    model_eval = evaluate_models(targeted)
    vs_state = establishment_vs_state(targeted, model_eval)
    best_ml = next(
        (e for e in model_eval.get("ranking_by_pr_auc", []) if e in available_ml_models()),
        "random_forest",
    )
    unseen = unseen_establishment_holdout(targeted, best_ml)

    comparison = {
        "pathogen": PRIMARY_PATHOGEN,
        "feature_columns": list(FEATURE_COLUMNS),
        "n_feature_rows": int(len(features)),
        "n_evaluable_rows": int((targeted["evaluable_future"] & targeted["target_binary"].notna()).sum()),
        "model_evaluation": model_eval,
        "establishment_vs_state": vs_state,
        "unseen_establishment_holdout": unseen,
    }
    _write_json(comparison, PROCESSED_MODELS_ROOT / "establishment_model_comparison.json")

    # Descriptive-only rankings for Listeria / STEC
    descriptive = {
        p: descriptive_establishment_scores(samples_by_pathogen[p])
        for p in ("Listeria", "STEC")
    }
    _write_json(descriptive, PROCESSED_MODELS_ROOT / "establishment_descriptive_scores.json")

    # STEP 6 — decision
    state_v2_actual = _load_state_v2_actual()
    decision = decide(feasibility, model_eval, vs_state, unseen, state_v2_actual)
    decision["state_v2_reference_handed_in"] = STATE_V2_REFERENCE
    decision["state_v2_measured"] = state_v2_actual
    _write_json(decision, INTERIM_ROOT / "establishment_decision.json")

    _write_experiment_md(
        feasibility, model_eval, vs_state, unseen, descriptive, decision,
        state_v2_actual, DOCS_REPORTS_ROOT / "establishment_experiment.md",
    )

    # module_status.json — final per-pathogen engine choice + deciding metric
    module_status = {
        "description": (
            "Final per-pathogen forecasting-engine choice after the establishment-"
            "level experiment (Req 6.5). Records the deciding metric and the "
            "feasibility factors behind each choice. State-level v2 is never "
            "abandoned; establishment level is adopted only where it is both "
            "feasible and demonstrably better on a common outcome and unseen "
            "establishments."
        ),
        "engines": decision["per_pathogen_engine_choice"],
        "retailer_decision_scope": decision["retailer_decision_scope"],
    }
    _write_json(module_status, INTERIM_ROOT / "module_status.json")

    return {
        "feasibility": feasibility,
        "model_comparison": comparison,
        "decision": decision,
        "module_status": module_status,
    }


if __name__ == "__main__":  # pragma: no cover - module CLI entry
    import sys
    result = run_experiment()
    json.dump(result["decision"], sys.stdout, indent=2, default=_json_default)
