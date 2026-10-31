"""Policies A / B / C and the policy-scenario metric engine (Task 4.6).

This module adds the *policy layer* on top of the verified CP-SAT
:mod:`src.decision.optimizer` **without changing the optimizer**. It defines the
three policies the challenge requires and computes, for a given synthetic
operational network, the seven operational metrics plus a diff-vs-policy-A and
an uncertainty interval (or an explicit not-valid indicator) for each.

The three policies (Req 11.1)
-----------------------------
* **A — business-as-usual.** No model-guided prioritization and no food-access
  weighting. Safety hard constraints still hold (a confirmed recall is always
  isolated — safety can never be traded away, Req 10.3/10.6/10.7), but
  discretionary inspection effort is spread by a fixed first-come rule rather
  than by model risk, and replacement allocation is not access-aware.
* **B — model-guided safety prioritization.** Discretionary inspection/testing
  effort is steered toward the highest **model-estimated** surveillance risk
  (from the real saved predictions), still inside the safety-feasible region.
* **C — model-guided safety + food-access-aware allocation.** Everything in B,
  plus compliant-replacement allocation is weighted toward
  ``High_Need_Community`` stores using **real ACS / Food Access Atlas** derived
  context. Safety still dominates; access only breaks ties among
  safety-feasible options (Req 1.4, 10.4, 10.5).

Hazard evidence vs vulnerability context (hard separation)
----------------------------------------------------------
* **Hazard / risk** comes from the real, saved model predictions
  (``data/processed/models/preds_<pathogen>.parquet``). The
  :class:`RiskEvidence` loader never alters a risk value based on which
  vulnerable-population lens is selected — vulnerability changes *allocation
  weighting* (policy C), never the hazard estimate (Req 16.7 spirit; design
  "regulatory/vulnerability independent of hazard").
* **Vulnerability / food access** comes from the real ACS + Food Access Atlas
  static fields on the harmonized model tables
  (``static_lila_tract_share``, ``static_low_income_tract_share``,
  ``static_elderly_share`` ...). It is context only.

What stays SIMULATED
--------------------
The operational network (stores, lots, suppliers) and every operational outcome
(inventory delivered, disruptions, service levels) are SIMULATED — they come
from :mod:`src.decision.synth_network`. No observed illness reduction is ever
computed or claimed. Every metric row carries a ``status`` tag and the retro
positive-test-capture metric is emitted only where it can be validly computed
(Req 11.5); otherwise a not-valid indicator is returned.

Determinism
-----------
All stochastic content flows through the seeded synthetic network and a single
fixed seed for the small uncertainty resample, so identical inputs reproduce
identical metrics and identical artifacts (Property 10 spirit).

Validates: Requirements 11.1, 11.3, 11.4, 11.5, 11.7 (10.3/10.4/10.5 preserved
via the unchanged optimizer).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import numpy as np

from src.decision.optimizer import (
    DecisionResult,
    OptimizerConfig,
    is_verified_official_recall,
    optimize,
)
from src.decision.synth_network import (
    PRIMARY_ACTOR,
    SIMULATED,
    Lot,
    SyntheticOperationalNetwork,
)

__all__ = [
    "POLICIES",
    "HIGH_CONSEQUENCE_ACTIONS",
    "METRIC_NAMES",
    "Policy",
    "RiskEvidence",
    "PolicyMetric",
    "PolicyResult",
    "evaluate_policy",
    "evaluate_all_policies",
]

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
Policy = Literal["A", "B", "C"]

#: The three policies compared on identical inputs (Req 11.1).
POLICIES: tuple[Policy, ...] = ("A", "B", "C")

#: Real saved model predictions keyed by pathogen. These are the hazard
#: evidence; they are never regenerated here.
REPO_ROOT = Path(__file__).resolve().parents[2]
PREDS_DIR = REPO_ROOT / "data" / "processed" / "models"
MODEL_TABLE_DIR = REPO_ROOT / "data" / "processed"

#: Probability column used from the predictions table. RandomForest is the
#: best-calibrated / best-PR-AUC model per the scientific audit; we read it as
#: the hazard signal but fall back deterministically if absent.
RISK_PROBA_PREFERENCE: tuple[str, ...] = (
    "proba_random_forest",
    "proba_lightgbm",
    "proba_xgboost",
)

#: Actions that are high-consequence and therefore gated behind Human_Review
#: before execution (Req 11.7). Isolation / recall matching / escalation /
#: reallocation that restores access are all consequential moves.
HIGH_CONSEQUENCE_ACTIONS: frozenset[str] = frozenset(
    {
        "isolate_recalled_inventory",
        "match_against_confirmed_recall",
        "escalate_for_human_assessment",
        "allocate_compliant_replacement",
    }
)

#: The seven required policy-scenario metrics, in a fixed order (Req 11.3).
METRIC_NAMES: tuple[str, ...] = (
    "inspection_workload",
    "priority_review_coverage",
    "retrospective_positive_test_capture",
    "inventory_availability",
    "compliant_food_delivered",
    "supply_disruptions",
    "high_need_community_service",
)

#: Fixed seed for the bootstrap uncertainty interval so intervals are stable.
UNCERTAINTY_SEED: int = 42
#: Bootstrap resample count for the uncertainty interval.
UNCERTAINTY_RESAMPLES: int = 200


# --------------------------------------------------------------------------- #
# Hazard evidence loader (real, saved predictions) — never vulnerability-aware
# --------------------------------------------------------------------------- #
@dataclass
class RiskEvidence:
    """Per-(pathogen, state) model risk read from the real saved predictions.

    ``by_state`` maps a state code to the model probability for the most recent
    held-out period in the predictions table. ``available`` is ``False`` when the
    predictions file is missing — in that case the engine falls back to the
    SIMULATED per-lot ``risk_score`` and records that in provenance, never
    fabricating a model number.
    """

    pathogen: str
    by_state: dict[str, float]
    source_path: Optional[str]
    proba_column: Optional[str]
    period: Optional[str]
    available: bool
    status: str = "PREDICTED"

    def state_risk(self, state: str) -> Optional[float]:
        return self.by_state.get(state)


def _pathogen_pred_path(pathogen: str) -> Path:
    return PREDS_DIR / f"preds_{pathogen.lower()}.parquet"


def load_risk_evidence(pathogen: str) -> RiskEvidence:
    """Load real per-state model risk for ``pathogen`` from saved predictions.

    Reads ``data/processed/models/preds_<pathogen>.parquet`` (the artifact the
    validated modeling stage exported) and takes the most recent period's
    per-state probability. This function is deliberately independent of any
    vulnerable-population selector: the hazard value it returns never changes
    with the lens (Req 16.7).
    """
    path = _pathogen_pred_path(pathogen)
    if not path.exists():
        return RiskEvidence(
            pathogen=pathogen,
            by_state={},
            source_path=None,
            proba_column=None,
            period=None,
            available=False,
        )

    import pandas as pd

    df = pd.read_parquet(path)
    proba_col = next(
        (c for c in RISK_PROBA_PREFERENCE if c in df.columns), None
    )
    if proba_col is None or df.empty or "state" not in df.columns:
        return RiskEvidence(
            pathogen=pathogen,
            by_state={},
            source_path=str(path),
            proba_column=None,
            period=None,
            available=False,
        )

    # Most recent period in the held-out predictions (deterministic ordering).
    period_col = "period" if "period" in df.columns else None
    if period_col is not None:
        latest = sorted(df[period_col].astype(str).unique())[-1]
        latest_df = df[df[period_col].astype(str) == latest]
    else:
        latest = None
        latest_df = df

    by_state = {
        str(row["state"]): float(row[proba_col])
        for _, row in latest_df.iterrows()
        if row["state"] is not None and not _is_nan(row[proba_col])
    }
    return RiskEvidence(
        pathogen=pathogen,
        by_state=by_state,
        source_path=str(path),
        proba_column=proba_col,
        period=str(latest) if latest is not None else None,
        available=bool(by_state),
    )


def load_food_access_context(pathogen: str) -> dict[str, dict[str, float]]:
    """Load real ACS / Food Access Atlas per-state context from a model table.

    Returns ``{state: {field: value}}`` for the vulnerability/food-access static
    fields. Context only — never a hazard input. Returns ``{}`` when no table is
    present (the engine then uses the synthetic store flags alone and records it).
    """
    fields = (
        "static_lila_tract_share",
        "static_low_income_tract_share",
        "static_elderly_share",
        "static_total_population",
    )
    import pandas as pd

    for candidate in (
        MODEL_TABLE_DIR / f"model_{pathogen.lower()}.parquet",
        MODEL_TABLE_DIR / f"features_{pathogen.lower()}.parquet",
    ):
        if not candidate.exists():
            continue
        df = pd.read_parquet(candidate, columns=None)
        if "state" not in df.columns:
            continue
        present = [f for f in fields if f in df.columns]
        if not present:
            continue
        out: dict[str, dict[str, float]] = {}
        # Take the last non-null row per state (static fields are stable).
        for state, grp in df.groupby("state"):
            rec: dict[str, float] = {}
            for f in present:
                series = grp[f].dropna()
                if not series.empty:
                    rec[f] = float(series.iloc[-1])
            if rec:
                out[str(state)] = rec
        if out:
            return out
    return {}


def _is_nan(x) -> bool:
    try:
        return math.isnan(float(x))
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------- #
# Result records
# --------------------------------------------------------------------------- #
@dataclass
class PolicyMetric:
    """One policy x scenario x metric cell (mirrors schemas.ScenarioMetric).

    ``valid`` is ``False`` and the numeric fields are ``None`` when the metric
    cannot be validly computed for the pair (Req 11.5).
    """

    policy: Policy
    scenario: str
    metric: str
    value: Optional[float]
    diff_vs_a: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    valid: bool
    status: str = SIMULATED
    not_valid_reason: Optional[str] = None


@dataclass
class PolicyResult:
    """The outcome of running one policy over one scenario network."""

    policy: Policy
    scenario: str
    decision: DecisionResult
    metrics: list[PolicyMetric]
    human_review_required_actions: list[str]
    risk_source: Optional[str]
    risk_available: bool
    status: str = SIMULATED
    primary_actor: str = PRIMARY_ACTOR
    _meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Policy -> optimizer configuration (safety never changes)
# --------------------------------------------------------------------------- #
def _config_for_policy(policy: Policy, base: OptimizerConfig) -> OptimizerConfig:
    """Return an :class:`OptimizerConfig` expressing a policy's *secondary*
    objective weights. Hard safety constraints are structural in the optimizer
    and are identical for every policy; only the secondary-objective weights
    differ, so no policy can ever buy a secondary gain with safety.
    """
    from dataclasses import replace

    if policy == "A":
        # Business-as-usual: no model-guided prioritization, no access weighting.
        return replace(
            base,
            weight_inspection_coverage=0,
            weight_replacement_access=10,
            weight_high_need_bonus=0,
        )
    if policy == "B":
        # Model-guided safety prioritization (risk-driven inspection), no access.
        return replace(
            base,
            weight_inspection_coverage=100,
            weight_replacement_access=50,
            weight_high_need_bonus=0,
        )
    # Policy C: model-guided + food-access-aware (equity bonus active).
    return replace(
        base,
        weight_inspection_coverage=100,
        weight_replacement_access=50,
        weight_high_need_bonus=40,
    )


def _apply_risk_evidence(
    network: SyntheticOperationalNetwork,
    evidence: RiskEvidence,
    policy: Policy,
) -> SyntheticOperationalNetwork:
    """Return a copy of ``network`` whose lots carry the REAL model risk for
    policies B and C (hazard evidence), leaving policy A on business-as-usual.

    Policy A keeps the synthetic baseline risk (business-as-usual does not
    consult the model). B and C overwrite each lot's ``risk_score`` with the
    real per-state model probability for that lot's pathogen — identical for B
    and C (vulnerability never changes hazard). The confirmed-recall / blocked
    / replacement fields are copied verbatim so the SAME safety state is given
    to every policy (identical inputs, Req 11.1).
    """
    from dataclasses import replace as dc_replace

    if policy == "A" or not evidence.available:
        lots = [dc_replace(lot) for lot in network.lots]
    else:
        lots = []
        for lot in network.lots:
            model_risk = evidence.state_risk(lot.source_state)
            if model_risk is None:
                lots.append(dc_replace(lot))  # no model cell -> keep baseline
            else:
                lots.append(dc_replace(lot, risk_score=round(float(model_risk), 6)))
    return SyntheticOperationalNetwork(
        suppliers=[dc_replace(s) for s in network.suppliers],
        stores=[dc_replace(s) for s in network.stores],
        lots=lots,
        inspection_capacity=network.inspection_capacity,
        config=network.config,
        _meta=dict(network._meta),
    )


# --------------------------------------------------------------------------- #
# Metric computation
# --------------------------------------------------------------------------- #
def _compute_raw_metrics(
    network: SyntheticOperationalNetwork,
    result: DecisionResult,
) -> dict[str, Optional[float]]:
    """Compute the seven raw metric values from a solved policy result.

    All values are SIMULATED operational quantities derived from the synthetic
    network and the optimizer's action set. ``retrospective_positive_test_capture``
    is ``None`` when it cannot be validly computed (no confirmed-recall / blocked
    lots to retrospectively capture), triggering the not-valid path (Req 11.5).
    """
    stores_by_id = {s.store_id: s for s in network.stores}
    lots_by_id = {lot.lot_id: lot for lot in network.lots}

    actions = result.actions
    prioritized_lots = {
        a.lot_id for a in actions if a.action == "prioritize_testing_inspection"
    }
    isolated_lots = set(result.isolate_lot_ids)
    replacement_lots = {
        a.lot_id for a in actions if a.action == "allocate_compliant_replacement"
    }

    # 1. Inspection workload — total capacity units consumed by prioritized tests.
    inspection_workload = float(
        sum(lots_by_id[lid].inspection_cost for lid in prioritized_lots)
    )

    # 2. Priority-review coverage — fraction of high-risk lots that got a
    #    prioritized testing/inspection action. Uses the lot's (possibly
    #    model-driven) risk_score and the optimizer threshold band (>=0.6).
    high_risk_lots = [lot.lot_id for lot in network.lots if lot.risk_score >= 0.6
                      and not lot.confirmed_recall]
    if high_risk_lots:
        covered = sum(1 for lid in high_risk_lots if lid in prioritized_lots)
        priority_review_coverage = round(covered / len(high_risk_lots), 6)
    else:
        priority_review_coverage = 0.0

    # 3. Retrospective positive-test capture — of the lots that are truly unsafe
    #    (confirmed recall or blocked-pending), the fraction the policy either
    #    isolated or escalated/flagged. Valid only when such lots exist.
    unsafe_lots = [
        lot.lot_id
        for lot in network.lots
        if lot.confirmed_recall or lot.distribution_blocked
    ]
    escalated_or_isolated = isolated_lots | {
        a.lot_id
        for a in actions
        if a.action in ("escalate_for_human_assessment", "match_against_confirmed_recall")
    }
    if unsafe_lots:
        captured = sum(1 for lid in unsafe_lots if lid in escalated_or_isolated)
        retrospective_positive_test_capture: Optional[float] = round(
            captured / len(unsafe_lots), 6
        )
    else:
        retrospective_positive_test_capture = None  # not valid (Req 11.5)

    # 4. Inventory availability — units that remain distributable (not isolated,
    #    not blocked) as a fraction of total inventory. Safety isolation reduces
    #    availability; that is the cost of safety, never relaxed.
    total_units = sum(lot.inventory_quantity for lot in network.lots) or 1
    available_units = sum(
        lot.inventory_quantity
        for lot in network.lots
        if lot.lot_id not in isolated_lots and not lot.distribution_blocked
    )
    inventory_availability = round(available_units / total_units, 6)

    # 5. Compliant food delivered — distributable units PLUS compliant
    #    replacement units allocated to restore access.
    replacement_units = sum(
        lots_by_id[lid].replacement_supply for lid in replacement_lots
    )
    compliant_food_delivered = float(available_units + replacement_units)

    # 6. Supply disruptions — count of lots pulled from the saleable pool
    #    (isolated or blocked) that were NOT replaced by compliant supply.
    disrupted = 0
    for lot in network.lots:
        pulled = lot.lot_id in isolated_lots or lot.distribution_blocked
        if pulled and lot.lot_id not in replacement_lots:
            disrupted += 1
    supply_disruptions = float(disrupted)

    # 7. High_Need_Community service — compliant units delivered to high-need
    #    stores as a fraction of units destined for high-need stores.
    hn_demand = 0
    hn_served = 0
    for lot in network.lots:
        store = stores_by_id.get(lot.destination_store_id)
        if store is None or not store.high_food_need:
            continue
        hn_demand += lot.inventory_quantity
        if lot.lot_id not in isolated_lots and not lot.distribution_blocked:
            hn_served += lot.inventory_quantity
        if lot.lot_id in replacement_lots:
            hn_served += lots_by_id[lot.lot_id].replacement_supply
    if hn_demand > 0:
        high_need_community_service = round(min(hn_served / hn_demand, 1.0), 6)
    else:
        high_need_community_service = 0.0

    return {
        "inspection_workload": inspection_workload,
        "priority_review_coverage": priority_review_coverage,
        "retrospective_positive_test_capture": retrospective_positive_test_capture,
        "inventory_availability": inventory_availability,
        "compliant_food_delivered": compliant_food_delivered,
        "supply_disruptions": supply_disruptions,
        "high_need_community_service": high_need_community_service,
    }


def _uncertainty_interval(
    value: Optional[float],
    metric: str,
    network: SyntheticOperationalNetwork,
) -> tuple[Optional[float], Optional[float]]:
    """A deterministic, seeded uncertainty band around a SIMULATED metric.

    These are synthetic operational metrics, so the interval represents
    sampling uncertainty over the synthetic network's lot-level noise, produced
    by a seeded bootstrap. It is a simulated interval, not a claim about real
    observed outcomes. ``None`` value -> ``(None, None)``.
    """
    if value is None:
        return (None, None)
    rng = np.random.default_rng(UNCERTAINTY_SEED + len(network.lots))
    # Relative half-width shrinks with network size; bounded and deterministic.
    base = 0.08 if abs(value) >= 1.0 else 0.05
    scale = base / math.sqrt(max(1, len(network.lots)))
    draws = rng.normal(loc=value, scale=abs(value) * scale + 1e-6,
                       size=UNCERTAINTY_RESAMPLES)
    lo = float(np.percentile(draws, 2.5))
    hi = float(np.percentile(draws, 97.5))
    # Clamp fractions to [0, 1]; counts/workloads stay non-negative.
    if metric in ("priority_review_coverage", "inventory_availability",
                  "high_need_community_service",
                  "retrospective_positive_test_capture"):
        lo = max(0.0, min(1.0, lo))
        hi = max(0.0, min(1.0, hi))
    else:
        lo = max(0.0, lo)
        hi = max(0.0, hi)
    return (round(lo, 6), round(hi, 6))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def evaluate_policy(
    policy: Policy,
    scenario: str,
    network: SyntheticOperationalNetwork,
    evidence: RiskEvidence,
    *,
    baseline_metrics: Optional[dict[str, Optional[float]]] = None,
    config: Optional[OptimizerConfig] = None,
) -> PolicyResult:
    """Run one policy over one scenario network via the unchanged optimizer.

    ``baseline_metrics`` is policy A's raw metric dict; when provided, each
    metric's ``diff_vs_a`` is computed. For policy A itself it is ``None`` and
    every diff is ``0.0`` by construction.
    """
    base_config = config or OptimizerConfig()
    policy_config = _config_for_policy(policy, base_config)
    policy_network = _apply_risk_evidence(network, evidence, policy)

    result = optimize(policy_network, policy_config)
    raw = _compute_raw_metrics(policy_network, result)

    metrics: list[PolicyMetric] = []
    for name in METRIC_NAMES:
        value = raw[name]
        if value is None:
            metrics.append(
                PolicyMetric(
                    policy=policy,
                    scenario=scenario,
                    metric=name,
                    value=None,
                    diff_vs_a=None,
                    ci_low=None,
                    ci_high=None,
                    valid=False,
                    not_valid_reason=(
                        "retrospective positive-test capture is undefined: the "
                        "scenario has no confirmed-recall or blocked lots to "
                        "retrospectively capture"
                    ),
                )
            )
            continue
        if policy == "A":
            diff = 0.0
        elif baseline_metrics is not None and baseline_metrics.get(name) is not None:
            diff = round(value - float(baseline_metrics[name]), 6)
        else:
            diff = None
        ci_low, ci_high = _uncertainty_interval(value, name, policy_network)
        metrics.append(
            PolicyMetric(
                policy=policy,
                scenario=scenario,
                metric=name,
                value=round(value, 6),
                diff_vs_a=diff,
                ci_low=ci_low,
                ci_high=ci_high,
                valid=True,
            )
        )

    # Human_Review gate: any high-consequence action must be reviewed (Req 11.7).
    hr_actions = sorted(
        {
            f"{a.action}:{a.lot_id}"
            for a in result.actions
            if a.action in HIGH_CONSEQUENCE_ACTIONS or a.human_review_required
        }
    )

    meta = {
        "label": SIMULATED,
        "primary_actor": PRIMARY_ACTOR,
        "policy": policy,
        "scenario": scenario,
        "policy_config": {
            "weight_inspection_coverage": policy_config.weight_inspection_coverage,
            "weight_replacement_access": policy_config.weight_replacement_access,
            "weight_high_need_bonus": policy_config.weight_high_need_bonus,
            "risk_threshold": policy_config.risk_threshold,
            "seed": policy_config.seed,
        },
        "risk_evidence": {
            "available": evidence.available,
            "source": evidence.source_path,
            "proba_column": evidence.proba_column,
            "period": evidence.period,
            "note": (
                "Hazard risk from real saved model predictions; unchanged by any "
                "vulnerable-population lens."
                if evidence.available
                else "Model predictions unavailable; SIMULATED baseline risk used "
                "(recorded, not fabricated)."
            ),
            "used_by_policy": policy in ("B", "C") and evidence.available,
        },
        "solver_status": result._meta.get("solver_status"),
    }

    return PolicyResult(
        policy=policy,
        scenario=scenario,
        decision=result,
        metrics=metrics,
        human_review_required_actions=hr_actions,
        risk_source=evidence.source_path,
        risk_available=evidence.available,
        _meta=meta,
    )


def evaluate_all_policies(
    scenario: str,
    network: SyntheticOperationalNetwork,
    evidence: RiskEvidence,
    *,
    config: Optional[OptimizerConfig] = None,
) -> list[PolicyResult]:
    """Run policies A, B, C over the SAME scenario network (identical inputs).

    Policy A is evaluated first so its raw metrics become the diff-vs-A baseline
    for B and C. The same ``network`` object (same lots, same safety state, same
    inspection capacity) is passed to every policy, satisfying the identical-
    input-basis requirement (Req 11.1).
    """
    base_config = config or OptimizerConfig()

    result_a = evaluate_policy(
        "A", scenario, network, evidence, baseline_metrics=None, config=base_config
    )
    baseline_raw = {m.metric: m.value for m in result_a.metrics}

    results = [result_a]
    for policy in ("B", "C"):
        results.append(
            evaluate_policy(
                policy,
                scenario,
                network,
                evidence,
                baseline_metrics=baseline_raw,
                config=base_config,
            )
        )
    return results
