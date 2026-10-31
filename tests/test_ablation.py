"""Tests for the data-source ablations (Task 3.9, Req 9.3, 9.4, 9.5).

Covers:

(a) exactly four configurations, named {fsis_only, fsis_cdc, fsis_noaa, full};
(b) feature-group classification by data source (FSIS / NOAA / static / CDC);
(c) **Property 6 — ablation marginal contributions preserve sign**: for
    constructed configs with KNOWN metric values the reported marginal equals
    ``config_metric - fsis_only_metric`` with the sign preserved, including
    negative contributions (never clamped / suppressed — Req 9.5);
(d) a MISSING CDC feature group yields a recorded gap (status "gap",
    marginal = None), NOT a fabricated number;
(e) an end-to-end run on a small synthetic model table produces all four
    configs, signed marginals, and a report without fabricating the CDC delta.

Property 6 uses Hypothesis to assert sign preservation across many metric
value pairs (>= 100 examples), including negatives and the exact zero boundary.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.pipeline import target as tg
from src.models.ablation import (
    ABLATION_CONFIGS,
    PRIMARY_METRIC,
    ablation_for_pathogen,
    classify_feature_group,
    config_feature_columns,
    group_features,
    run_ablations,
    signed_marginal_contribution,
)


# --------------------------------------------------------------------------- #
# (a) Exactly four configurations with the exact names
# --------------------------------------------------------------------------- #

def test_exactly_four_ablation_configs():
    assert len(ABLATION_CONFIGS) == 4
    assert set(ABLATION_CONFIGS) == {"fsis_only", "fsis_cdc", "fsis_noaa", "full"}


# --------------------------------------------------------------------------- #
# (b) Feature-group classification by data source
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "column,expected",
    [
        ("routine_positivity_lag1", "fsis"),
        ("context_forcause_positivity_lag1", "fsis"),
        ("context_exploratory_samples_lag1", "fsis"),
        ("national_routine_positivity_lag1", "fsis"),
        ("season_sin", "fsis"),
        ("period_of_year", "fsis"),
        ("calendar_year", "fsis"),
        ("geo_state", "fsis"),
        ("geo_region", "fsis"),
        ("weather_tmax_mean_lag1", "noaa"),
        ("weather_prcp_anomaly_lag1", "noaa"),
        ("static_total_population", "static"),
        ("static_elderly_share", "static"),
        ("cdc_nors_rate_lag1", "cdc"),
    ],
)
def test_classify_feature_group(column, expected):
    assert classify_feature_group(column) == expected


def test_group_features_partitions_real_column_set():
    feats = [
        "routine_positivity_lag1", "season_sin", "geo_state",
        "weather_tmax_mean_lag1", "weather_prcp_total_lag1",
        "static_total_population", "static_elderly_share",
    ]
    groups = group_features(feats)
    assert set(groups["fsis"]) == {"routine_positivity_lag1", "season_sin", "geo_state"}
    assert set(groups["noaa"]) == {"weather_tmax_mean_lag1", "weather_prcp_total_lag1"}
    assert set(groups["static"]) == {"static_total_population", "static_elderly_share"}
    assert groups["cdc"] == []  # no CDC columns in the real matrix


def test_config_feature_columns_compose_groups():
    groups = {
        "fsis": ["routine_positivity_lag1", "season_sin"],
        "cdc": [],
        "noaa": ["weather_tmax_mean_lag1"],
        "static": ["static_total_population"],
        "other": [],
    }
    assert set(config_feature_columns("fsis_only", groups)) == {
        "routine_positivity_lag1", "season_sin"
    }
    # no CDC columns -> fsis_cdc degenerates to the fsis set (gap handled upstream)
    assert set(config_feature_columns("fsis_cdc", groups)) == {
        "routine_positivity_lag1", "season_sin"
    }
    assert set(config_feature_columns("fsis_noaa", groups)) == {
        "routine_positivity_lag1", "season_sin", "weather_tmax_mean_lag1"
    }
    assert set(config_feature_columns("full", groups)) == {
        "routine_positivity_lag1", "season_sin",
        "weather_tmax_mean_lag1", "static_total_population",
    }


# --------------------------------------------------------------------------- #
# (c) PROPERTY 6 — ablation marginal contributions preserve sign
# **Validates: Requirements 9.4, 9.5**
# --------------------------------------------------------------------------- #

@settings(max_examples=200)
@given(
    config_metric=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    base_metric=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_property6_marginal_preserves_sign(config_metric, base_metric):
    """marginal == config - base, with the sign preserved (incl. negative)."""
    marginal = signed_marginal_contribution(config_metric, base_metric)
    expected = config_metric - base_metric
    assert marginal == pytest.approx(expected)
    # sign is preserved exactly — never clamped to zero or suppressed (Req 9.5)
    assert np.sign(marginal) == np.sign(expected)
    if config_metric < base_metric:
        assert marginal < 0.0  # a worse config reports a NEGATIVE contribution
    elif config_metric > base_metric:
        assert marginal > 0.0
    else:
        assert marginal == 0.0


def test_property6_explicit_negative_examples():
    # A config that is worse than FSIS-only MUST report a negative marginal.
    assert signed_marginal_contribution(0.30, 0.50) == pytest.approx(-0.20)
    assert signed_marginal_contribution(0.0, 0.75) == pytest.approx(-0.75)
    # equal -> exactly zero; better -> positive
    assert signed_marginal_contribution(0.5, 0.5) == 0.0
    assert signed_marginal_contribution(0.9, 0.4) == pytest.approx(0.5)


def test_marginal_none_when_metric_unavailable():
    # An unavailable metric propagates to None (not fabricated as 0).
    assert signed_marginal_contribution(None, 0.5) is None
    assert signed_marginal_contribution(0.5, None) is None
    assert signed_marginal_contribution(None, None) is None


# --------------------------------------------------------------------------- #
# Synthetic model table + end-to-end ablation run
# --------------------------------------------------------------------------- #

def _monthly_periods(n: int, start_year: int = 2015) -> list[str]:
    out: list[str] = []
    y, m = start_year, 1
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _make_model_table(
    n_periods: int = 48,
    states=("AA", "BB", "CC"),
    *,
    include_cdc: bool = False,
    seed: int = 11,
) -> pd.DataFrame:
    """Deterministic synthetic model table mirroring the real model_* schema.

    By default carries FSIS + NOAA(weather, NaN) + static columns and NO CDC
    columns (matching reality). ``include_cdc=True`` adds a ``cdc_*`` feature so
    the "CDC present" branch can also be exercised.
    """
    rng = np.random.default_rng(seed)
    periods = _monthly_periods(n_periods)
    regions = {"AA": "South", "BB": "West", "CC": "Midwest"}
    rows: list[dict] = []
    for state in states:
        for i, period in enumerate(periods):
            lag1 = float(rng.uniform(0.0, 0.3))
            trailing = float(rng.uniform(0.0, 0.3))
            prob = 1.0 / (1.0 + np.exp(-(6.0 * (lag1 - trailing))))
            y = int(rng.uniform() < prob)
            row = {
                "pathogen": "Test",
                "state": state,
                "period": period,
                "period_start": tg.period_start(period),
                "cutoff": tg.period_start(period),
                "resolution": "monthly",
                "outcome_routine_samples": 100.0,
                "outcome_routine_positives": 10.0,
                "outcome_routine_positivity_rate": 0.1,
                # FSIS features
                "routine_positivity_lag1": lag1,
                "routine_positivity_trailing12m_mean": trailing,
                "routine_samples_lag1": float(rng.integers(50, 150)),
                "season_sin": np.sin(2 * np.pi * (i % 12) / 12),
                "season_cos": np.cos(2 * np.pi * (i % 12) / 12),
                "period_of_year": (i % 12) + 1,
                "calendar_year": tg.period_start(period).year,
                "geo_state": state,
                "geo_region": regions[state],
                # NOAA (mostly NaN like reality)
                "weather_tmax_mean_lag1": np.nan,
                "weather_prcp_total_lag1": np.nan,
                # static ACS/Atlas context
                "static_total_population": float(rng.integers(1_000_000, 5_000_000)),
                "static_elderly_share": float(rng.uniform(0.1, 0.2)),
                # label/target bookkeeping
                "baseline": trailing,
                "y_next_positivity": 0.1,
                "next_routine_samples": 100.0,
                "next_period": period,
                "labelable": True,
                "exclusion_reason": "",
                "y_elevated": pd.array([y], dtype="Int64")[0],
                # v2 label/target bookkeeping (mirrors real model_* schema)
                "labelable_v2": True,
                "y_elevated_v2": pd.array([y], dtype="Int64")[0],
                "smoothed_next_positivity": 0.1,
                "next_routine_positives": 10.0,
                "v2_threshold": 0.2,
                "exclusion_reason_v2": "",
            }
            if include_cdc:
                row["cdc_nors_rate_lag1"] = float(rng.uniform(0.0, 1.0))
            rows.append(row)
    df = pd.DataFrame(rows)
    df["y_elevated"] = df["y_elevated"].astype("Int64")
    df["y_elevated_v2"] = df["y_elevated_v2"].astype("Int64")
    return df


def _write_table(df: pd.DataFrame, processed: Path, slug: str) -> None:
    processed.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(processed / f"model_{slug}.parquet", index=False)
    except Exception:
        df.to_csv(processed / f"model_{slug}.csv", index=False)


# --------------------------------------------------------------------------- #
# (d) Missing CDC group -> recorded gap, not a fabricated number
# --------------------------------------------------------------------------- #

def test_missing_cdc_group_records_gap_not_number(tmp_path):
    processed = tmp_path / "processed"
    models = processed / "models"
    _write_table(_make_model_table(include_cdc=False), processed, "salmonella")

    res = ablation_for_pathogen(
        "Salmonella", processed_root=processed, models_root=models, write=False
    )

    # exactly the four configs are present
    assert set(res["configs"].keys()) == {"fsis_only", "fsis_cdc", "fsis_noaa", "full"}

    cdc = res["configs"]["fsis_cdc"]
    assert cdc["status"] == "gap"
    assert cdc["cdc_features_available"] is False
    assert cdc["metrics"] is None
    # the marginal is NOT fabricated: it is None, never 0.0 or a made-up value
    assert cdc["marginal_contribution_pr_auc"] is None
    assert res["cdc_features_available"] is False


def test_cdc_present_branch_is_evaluated(tmp_path):
    processed = tmp_path / "processed"
    models = processed / "models"
    _write_table(_make_model_table(include_cdc=True), processed, "salmonella")

    res = ablation_for_pathogen(
        "Salmonella", processed_root=processed, models_root=models, write=False
    )
    cdc = res["configs"]["fsis_cdc"]
    assert cdc["status"] == "evaluated"
    assert res["cdc_features_available"] is True
    # when CDC exists, the marginal is a real signed number (not None)
    assert cdc["marginal_contribution_pr_auc"] is not None


# --------------------------------------------------------------------------- #
# (e) End-to-end: four configs, signed marginals, fsis_only baseline is zero
# --------------------------------------------------------------------------- #

def test_end_to_end_ablation_signed_marginals(tmp_path):
    processed = tmp_path / "processed"
    models = processed / "models"
    for slug in ("salmonella", "listeria", "stec"):
        _write_table(_make_model_table(include_cdc=False), processed, slug)

    results = run_ablations(
        processed_root=processed, models_root=models, write=True
    )
    assert set(results["configs"]) == {"fsis_only", "fsis_cdc", "fsis_noaa", "full"}

    for pathogen in ("Salmonella", "Listeria", "STEC"):
        res = results["per_pathogen"][pathogen]
        cfgs = res["configs"]
        # baseline marginal vs itself is exactly zero
        assert cfgs["fsis_only"]["marginal_contribution_pr_auc"] == 0.0
        # evaluated configs report a signed numeric marginal; gap reports None
        assert cfgs["fsis_cdc"]["marginal_contribution_pr_auc"] is None
        for cfg in ("fsis_noaa", "full"):
            m = cfgs[cfg]["marginal_contribution_pr_auc"]
            base = cfgs["fsis_only"]["metrics"]["pr_auc"]
            this = cfgs[cfg]["metrics"]["pr_auc"]
            if base is not None and this is not None:
                assert m == pytest.approx(this - base)

    # the combined report was written
    assert Path(results["report_path"]).exists()


def test_report_names_cdc_gap_and_noaa(tmp_path):
    processed = tmp_path / "processed"
    models = processed / "models"
    report = tmp_path / "ablation.md"
    for slug in ("salmonella", "listeria", "stec"):
        _write_table(_make_model_table(include_cdc=False), processed, slug)

    from src.models.ablation import write_ablation_report

    results = run_ablations(processed_root=processed, models_root=models, write=False)
    write_ablation_report(results, out_path=report)
    text = report.read_text(encoding="utf-8")
    assert "CDC gap" in text
    assert "NOAA" in text
    assert "fsis_cdc" in text
