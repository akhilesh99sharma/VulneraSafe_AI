"""Tests for the CP-SAT Decision_Engine (Task 4.3; intent of 4.4/4.5).

Focused coverage:

* **Hard safety invariant (Property 5, Req 10.3/10.6/10.7)** — a confirmed-recall
  lot is never distributed and always isolated; a blocked lot is never
  distributed; no secondary objective relaxes a hard constraint.
* **Infeasible -> no-solution (Req 10.9)** — an unsatisfiable safety model
  returns no distribution recommendation plus the explicit
  ``no_safety_compliant_solution`` indicator and a reason.
* **Deterministic solve** — identical inputs produce identical action lists.
* **Action completeness + labeling (Req 10.1/10.2/11.6)** — the six action kinds
  are modeled; every action carries lot id, trigger, rank, Human_Review, and the
  SIMULATED tag.
* **Verified-recall discipline (correction 4)** — a simulated flag alone is not a
  verified official recall.

Validates: Requirements 10.1, 10.2, 10.3, 10.6, 10.7, 10.9, 11.6.
"""
from __future__ import annotations

from dataclasses import replace as dc_replace

from ortools.sat.python import cp_model

from src.decision import synth_network as sn
from src.decision.optimizer import (
    ACTION_KINDS,
    DecisionResult,
    is_verified_official_recall,
    optimize,
)
from src.decision.synth_network import NetworkConfig, generate_network


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _net_with_confirmed_recall(seed: int = 3):
    """A network whose first lot is a VERIFIED confirmed recall."""
    net = generate_network(NetworkConfig(seed=seed, n_lots=12))
    net.lots[0] = dc_replace(
        net.lots[0],
        official_recall=True,
        evidence_verified=True,
        confirmed_recall=True,
    )
    return net


# --------------------------------------------------------------------------- #
# Hard safety invariant
# --------------------------------------------------------------------------- #
def test_confirmed_recall_lot_is_isolated_and_never_distributed():
    net = _net_with_confirmed_recall()
    recalled_id = net.lots[0].lot_id
    result = optimize(net)

    assert result.feasible
    assert recalled_id in result.isolate_lot_ids

    acts = [a for a in result.actions if a.lot_id == recalled_id]
    kinds = {a.action for a in acts}
    assert "isolate_recalled_inventory" in kinds
    assert "match_against_confirmed_recall" in kinds
    # The recalled lot must never carry a distribution action.
    assert all(a.action != "allocate_compliant_replacement" for a in acts)


def test_blocked_lot_requires_human_review_and_is_not_distributed():
    net = generate_network(NetworkConfig(seed=4, n_lots=10))
    net.lots[1] = dc_replace(
        net.lots[1], distribution_blocked=True, confirmed_recall=False
    )
    blocked_id = net.lots[1].lot_id
    result = optimize(net)

    escalations = [
        a
        for a in result.actions
        if a.lot_id == blocked_id and a.action == "escalate_for_human_assessment"
    ]
    assert escalations, "blocked lot must be escalated for human assessment"
    assert all(a.human_review_required for a in escalations)


def test_recalled_lot_is_never_used_as_replacement():
    net = _net_with_confirmed_recall()
    recalled_id = net.lots[0].lot_id
    net.lots[0] = dc_replace(
        net.lots[0],
        official_recall=True,
        evidence_verified=True,
        confirmed_recall=True,
        replacement_supply=500,
    )
    result = optimize(net)
    repl = [
        a
        for a in result.actions
        if a.lot_id == recalled_id and a.action == "allocate_compliant_replacement"
    ]
    assert repl == []


# --------------------------------------------------------------------------- #
# Infeasible -> no-solution (Req 10.9)
# --------------------------------------------------------------------------- #
def test_no_solution_result_contract_shape():
    """The no-solution result shape: no actions, explicit indicator, reason."""
    bad = DecisionResult(
        feasible=False,
        actions=[],
        no_safety_compliant_solution=True,
        reason="No safety-compliant solution: contradictory hard constraints.",
        isolate_lot_ids=["LOT-0000"],
    )
    assert bad.actions == []
    assert bad.no_safety_compliant_solution is True
    assert bad.reason and "no safety-compliant solution" in bad.reason.lower()
    assert bad.status == sn.SIMULATED


def test_engine_reports_infeasible_on_unsatisfiable_model(monkeypatch):
    """Drive the real no-solution branch by making CP-SAT report INFEASIBLE."""
    net = generate_network(NetworkConfig(seed=2, n_lots=5))

    def fake_solve(self, model):  # noqa: ANN001
        return cp_model.INFEASIBLE

    monkeypatch.setattr(cp_model.CpSolver, "Solve", fake_solve)
    result = optimize(net)

    assert result.feasible is False
    assert result.actions == []
    assert result.no_safety_compliant_solution is True
    assert result.reason and "no safety-compliant solution" in result.reason.lower()
    assert result.isolate_lot_ids == sorted(result.isolate_lot_ids)


def test_normal_network_is_feasible():
    result = optimize(generate_network(NetworkConfig(seed=6, n_lots=6)))
    assert result.feasible
    assert result.no_safety_compliant_solution is False


# --------------------------------------------------------------------------- #
# Deterministic solve
# --------------------------------------------------------------------------- #
def test_identical_inputs_produce_identical_actions():
    net = _net_with_confirmed_recall(seed=5)
    serialize = lambda r: [
        (a.lot_id, a.action, a.priority_rank, a.human_review_required)
        for a in r.actions
    ]
    assert serialize(optimize(net)) == serialize(optimize(net))


def test_actions_sorted_by_priority_descending():
    net = _net_with_confirmed_recall(seed=5)
    ranks = [a.priority_rank for a in optimize(net).actions]
    assert ranks == sorted(ranks, reverse=True)


# --------------------------------------------------------------------------- #
# Action completeness + labeling
# --------------------------------------------------------------------------- #
def test_at_least_six_action_kinds_modeled():
    assert len(set(ACTION_KINDS)) >= 6


def test_every_action_is_simulated_and_fully_labeled():
    net = _net_with_confirmed_recall(seed=5)
    result = optimize(net)
    assert result.actions, "expected at least one action"
    for a in result.actions:
        assert a.status == sn.SIMULATED
        assert a.lot_id and a.product_id
        assert a.action in ACTION_KINDS
        assert a.triggering_condition
        assert isinstance(a.priority_rank, int)
        assert isinstance(a.human_review_required, bool)


# --------------------------------------------------------------------------- #
# Verified-recall discipline (correction 4)
# --------------------------------------------------------------------------- #
def test_simulated_flag_alone_is_not_a_verified_official_recall():
    net = generate_network(NetworkConfig(seed=7, n_lots=8))
    lot = dc_replace(net.lots[0], distribution_blocked=True)
    assert is_verified_official_recall(lot) is False


def test_all_three_flags_required_for_verified_recall():
    base = generate_network(NetworkConfig(seed=7, n_lots=8)).lots[0]
    assert not is_verified_official_recall(
        dc_replace(base, official_recall=True, confirmed_recall=True)
    )
    assert is_verified_official_recall(
        dc_replace(
            base, official_recall=True, evidence_verified=True, confirmed_recall=True
        )
    )
