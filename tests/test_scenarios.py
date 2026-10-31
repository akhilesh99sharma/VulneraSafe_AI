"""Focused tests for policies A/B/C and the three scenarios (Task 4.6).

Coverage:
* **Identical input basis (Req 11.1)** — all three policies for a scenario are
  evaluated against the SAME network object (same lots, same safety state, same
  capacity).
* **Hard-safety preservation (Req 10.3/10.6/10.7, Property 5)** — a confirmed
  recall lot is isolated and never distributed under EVERY policy; safety never
  relaxed to improve a secondary objective.
* **Metric / diff arithmetic (Req 11.3/11.4)** — diff_vs_a equals value minus
  policy A's value; policy A diffs are all 0.0; every valid metric carries an
  uncertainty interval bracketing its value.
* **Simulated labeling (Req 11.6, 16.6)** — the artifact and every record are
  SIMULATED; the Listeria recall is labeled a SIMULATED verified-evidence
  scenario, not a live official regulatory alert.
* **Human_Review gates (Req 11.7)** — the verified-recall scenario produces
  high-consequence actions that require Human_Review.
* **Not-valid indicator (Req 11.5)** — retrospective positive-test capture is
  omitted with a not-valid reason when no unsafe lots exist.
* **Deterministic output** — building the artifact twice is byte-identical.

These tests do NOT modify or re-run the verified optimizer or any model
artifact; they only read the saved predictions through the policy engine.
"""
from __future__ import annotations

import json

import pytest

from src.decision import scenarios as sc
from src.decision.policies import (
    METRIC_NAMES,
    POLICIES,
    evaluate_all_policies,
    load_risk_evidence,
)
from src.decision.synth_network import SIMULATED


# --------------------------------------------------------------------------- #
# Identical input basis
# --------------------------------------------------------------------------- #
def test_all_policies_share_identical_scenario_network():
    spec = sc.SCENARIOS[0]
    network = sc.build_scenario_network(spec)
    evidence = load_risk_evidence(spec.pathogen)

    # Snapshot the safety-relevant state of the input network.
    before = [
        (lot.lot_id, lot.confirmed_recall, lot.distribution_blocked,
         lot.replacement_supply, lot.inventory_quantity)
        for lot in network.lots
    ]
    before_capacity = network.inspection_capacity

    results = evaluate_all_policies(spec.scenario_id, network, evidence)

    # The shared network object is unchanged after evaluating all policies:
    # each policy works on its own internal copy (identical inputs, no mutation).
    after = [
        (lot.lot_id, lot.confirmed_recall, lot.distribution_blocked,
         lot.replacement_supply, lot.inventory_quantity)
        for lot in network.lots
    ]
    assert before == after
    assert network.inspection_capacity == before_capacity
    assert [r.policy for r in results] == list(POLICIES)


# --------------------------------------------------------------------------- #
# Hard-safety preservation under every policy
# --------------------------------------------------------------------------- #
def test_confirmed_recall_isolated_under_every_policy():
    spec = sc.SCENARIOS[0]  # listeria_rte_recall, has a verified confirmed recall
    network = sc.build_scenario_network(spec)
    recall_ids = {lot.lot_id for lot in network.lots if lot.confirmed_recall}
    assert recall_ids, "scenario 1 must contain a confirmed recall lot"

    evidence = load_risk_evidence(spec.pathogen)
    for pr in evaluate_all_policies(spec.scenario_id, network, evidence):
        # Every confirmed-recall lot is isolated and never distributed.
        assert recall_ids.issubset(set(pr.decision.isolate_lot_ids)), pr.policy
        distributed = {
            a.lot_id for a in pr.decision.actions
            if a.action == "allocate_compliant_replacement"
        }
        # A recalled lot is never itself used as replacement supply.
        assert not (recall_ids & distributed), pr.policy
        assert pr.decision.feasible


def test_safety_identical_across_policies():
    """The set of isolated (safety-forced) lots is the same for A/B/C: safety
    is structural and never changes with the secondary-objective policy."""
    spec = sc.SCENARIOS[0]
    network = sc.build_scenario_network(spec)
    evidence = load_risk_evidence(spec.pathogen)
    isolated_sets = [
        set(pr.decision.isolate_lot_ids)
        for pr in evaluate_all_policies(spec.scenario_id, network, evidence)
    ]
    assert isolated_sets[0] == isolated_sets[1] == isolated_sets[2]


# --------------------------------------------------------------------------- #
# Metric / diff arithmetic
# --------------------------------------------------------------------------- #
def test_diff_vs_a_arithmetic_and_baseline_zero():
    spec = sc.SCENARIOS[2]  # stec_beef_high_need exercises access weighting
    network = sc.build_scenario_network(spec)
    evidence = load_risk_evidence(spec.pathogen)
    results = evaluate_all_policies(spec.scenario_id, network, evidence)
    by_policy = {r.policy: r for r in results}

    a_values = {m.metric: m.value for m in by_policy["A"].metrics}

    # Policy A: every diff is exactly 0.0 for valid metrics.
    for m in by_policy["A"].metrics:
        if m.valid:
            assert m.diff_vs_a == 0.0

    # Policies B and C: diff_vs_a == value - A.value (within float tolerance).
    for policy in ("B", "C"):
        for m in by_policy[policy].metrics:
            if m.valid and a_values[m.metric] is not None:
                assert m.diff_vs_a == pytest.approx(
                    round(m.value - a_values[m.metric], 6), abs=1e-6
                )


def test_valid_metric_has_bracketing_uncertainty_interval():
    for spec in sc.SCENARIOS:
        network = sc.build_scenario_network(spec)
        evidence = load_risk_evidence(spec.pathogen)
        for pr in evaluate_all_policies(spec.scenario_id, network, evidence):
            for m in pr.metrics:
                if m.valid:
                    assert m.value is not None
                    assert m.ci_low is not None and m.ci_high is not None
                    assert m.ci_low <= m.value <= m.ci_high, (
                        spec.scenario_id, pr.policy, m.metric
                    )
                else:
                    assert m.value is None and m.ci_low is None and m.ci_high is None
                    assert m.not_valid_reason


def test_all_seven_metrics_present_per_policy():
    spec = sc.SCENARIOS[1]
    network = sc.build_scenario_network(spec)
    evidence = load_risk_evidence(spec.pathogen)
    for pr in evaluate_all_policies(spec.scenario_id, network, evidence):
        names = [m.metric for m in pr.metrics]
        assert names == list(METRIC_NAMES)


# --------------------------------------------------------------------------- #
# Not-valid indicator (Req 11.5)
# --------------------------------------------------------------------------- #
def test_retro_capture_not_valid_when_no_unsafe_lots():
    # Salmonella limited-inspection scenario has no confirmed-recall / blocked
    # lots, so retrospective positive-test capture is not validly computable.
    spec = sc.SCENARIOS[1]
    network = sc.build_scenario_network(spec)
    assert not any(
        lot.confirmed_recall or lot.distribution_blocked for lot in network.lots
    )
    evidence = load_risk_evidence(spec.pathogen)
    for pr in evaluate_all_policies(spec.scenario_id, network, evidence):
        retro = next(
            m for m in pr.metrics
            if m.metric == "retrospective_positive_test_capture"
        )
        assert retro.valid is False
        assert retro.value is None
        assert retro.not_valid_reason


# --------------------------------------------------------------------------- #
# Simulated labeling + verified-evidence (not live alert)
# --------------------------------------------------------------------------- #
def test_artifact_is_simulated_and_recall_is_not_live_alert():
    runs = sc.run_all_scenarios()
    payload = sc.scenario_comparison_dict(runs)
    assert payload["status"] == SIMULATED
    assert payload["label"] == SIMULATED
    for scen in payload["scenarios"]:
        for pol in scen["policies"]:
            assert pol["status"] == SIMULATED
            for m in pol["metrics"]:
                assert m["status"] == SIMULATED

    listeria = next(
        s for s in payload["scenarios"] if s["scenario_id"] == "listeria_rte_recall"
    )
    assert listeria["verified_recall"] is True
    assert listeria["live_official_recall"] is False
    assert "SIMULATED" in listeria["recall_labeling_note"]
    assert "not" in listeria["recall_labeling_note"].lower()


def test_no_observed_illness_reduction_metric():
    # The metric vocabulary must not include any observed-illness-outcome claim.
    joined = " ".join(METRIC_NAMES).lower()
    for forbidden in ("illness", "cases_prevented", "observed_reduction",
                      "lives_saved"):
        assert forbidden not in joined


# --------------------------------------------------------------------------- #
# Human_Review gates (Req 11.7)
# --------------------------------------------------------------------------- #
def test_verified_recall_scenario_requires_human_review():
    spec = sc.SCENARIOS[0]
    network = sc.build_scenario_network(spec)
    evidence = load_risk_evidence(spec.pathogen)
    for pr in evaluate_all_policies(spec.scenario_id, network, evidence):
        assert pr.human_review_required_actions, pr.policy
        # Every gated action is a confirmed high-consequence action.
        assert all(":" in a for a in pr.human_review_required_actions)


# --------------------------------------------------------------------------- #
# Deterministic output
# --------------------------------------------------------------------------- #
def test_comparison_artifact_is_deterministic(tmp_path):
    runs1 = sc.run_all_scenarios()
    runs2 = sc.run_all_scenarios()
    json1 = json.dumps(sc.scenario_comparison_dict(runs1), sort_keys=True)
    json2 = json.dumps(sc.scenario_comparison_dict(runs2), sort_keys=True)
    assert json1 == json2

    paths_a = sc.write_comparison_artifacts(
        runs1, web_data_dir=tmp_path / "a", synthetic_dir=tmp_path / "a_syn"
    )
    paths_b = sc.write_comparison_artifacts(
        runs2, web_data_dir=tmp_path / "b", synthetic_dir=tmp_path / "b_syn"
    )
    assert (paths_a["json"].read_text(encoding="utf-8")
            == paths_b["json"].read_text(encoding="utf-8"))
    assert (paths_a["csv"].read_text(encoding="utf-8")
            == paths_b["csv"].read_text(encoding="utf-8"))
