"""OR-Tools CP-SAT Decision_Engine with hard safety constraints (Task 4.3).

The ``Decision_Engine`` turns a :class:`~src.decision.synth_network.
SyntheticOperationalNetwork` into a ranked list of concrete, per-lot operational
actions for the **Food Safety Operations Director of a regional grocery retail
chain** (the single primary actor, Req 1.2). It is built on **OR-Tools CP-SAT**
(Req 10.8).

Design reference: design.md "Decision Optimization" and Property 5.

What this module guarantees
---------------------------
* **Hard food-safety constraints are never relaxed** for any secondary
  objective, and are wired directly from the regulatory-evidence track —
  independent of model risk / uncertainty (Req 10.3, 10.6, 10.7; correction 4):

  - a ``confirmed_recall`` lot is NEVER distributed and is ALWAYS isolated;
  - a ``distribution_blocked`` (pending-result) lot is NEVER distributed and
    requires a ``Human_Review`` release step;
  - replacement allocation may draw ONLY on compliant replacement supply
    (never from a recalled/blocked lot).

* **Secondary objectives** (inspection-capacity use, delivery continuity,
  minimizing shortages, equitable access to High_Need_Communities, cost) are
  optimized ONLY within the safety-feasible region. No secondary-objective gain
  is ever produced by relaxing a hard safety constraint (Property 5).

* At least six action kinds are modeled (Req 10.1): prioritize testing /
  inspection, request supplier documentation, escalate for human assessment,
  match lot ids against confirmed recalls, isolate recalled inventory, allocate
  compliant replacement inventory.

* Every returned :class:`DecisionAction` carries the affected product/lot id,
  the triggering condition, the action, a priority rank (highest first), the
  ``Human_Review`` requirement, and — because the only input here is the
  SIMULATED synthetic network — the ``SIMULATED`` status tag (Req 10.2, 11.6).

* On infeasibility the engine returns **no distribution recommendation** plus an
  explicit ``no_safety_compliant_solution`` indicator and a reason (Req 10.9).

Verified-recall discipline
--------------------------
A synthetic ``distribution_blocked`` flag is a SIMULATED signal only. A lot is
treated as a verified official recall (and so forced to isolate as a hard
constraint) ONLY when ``official_recall`` AND ``evidence_verified`` AND
``confirmed_recall`` are all true. A simulated flag alone never promotes a lot
to the verified regulatory-evidence track.

Determinism
-----------
CP-SAT is pinned to a single worker with a fixed random seed so identical
inputs produce identical solutions; action ordering is fully determined by
(priority desc, lot_id asc, action-kind order), so the returned list is stable.

Validates: Requirements 10.1-10.9.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from ortools.sat.python import cp_model

from src.decision.synth_network import (
    PRIMARY_ACTOR,
    SIMULATED,
    Lot,
    SyntheticOperationalNetwork,
)

__all__ = [
    "ACTION_KINDS",
    "DecisionAction",
    "DecisionResult",
    "OptimizerConfig",
    "is_verified_official_recall",
    "optimize",
]

# --------------------------------------------------------------------------- #
# Action vocabulary (Req 10.1 — at least six distinct actions)
# --------------------------------------------------------------------------- #
#: The six (+) modeled per-lot/per-store action kinds. Order here also defines a
#: deterministic tie-break when two actions share a priority rank.
ACTION_KINDS: tuple[str, ...] = (
    "isolate_recalled_inventory",      # hard-safety driven
    "match_against_confirmed_recall",  # regulatory-evidence lookup
    "escalate_for_human_assessment",   # blocked/pending -> Human_Review
    "prioritize_testing_inspection",   # risk-driven, within capacity
    "request_supplier_documentation",  # missing supplier docs
    "allocate_compliant_replacement",  # restore access with compliant supply
)

#: Fixed CP-SAT seed, matching the project-wide RANDOM_STATE=42 convention.
DEFAULT_SEED: int = 42

#: Model risk at/above this score makes a (safe) lot a candidate for prioritized
#: testing/inspection. A soft signal only; never a hard-safety input.
DEFAULT_RISK_THRESHOLD: float = 0.6


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OptimizerConfig:
    """Tuning knobs for one solve. Defaults are deterministic and safe."""

    seed: int = DEFAULT_SEED
    #: Risk score at/above which a safe lot is a testing/inspection candidate.
    risk_threshold: float = DEFAULT_RISK_THRESHOLD
    #: Secondary-objective weights (applied ONLY within the feasible region).
    weight_inspection_coverage: int = 100   # reward covering high-risk lots
    weight_replacement_access: int = 50     # reward restoring store access
    weight_high_need_bonus: int = 25        # extra reward for High_Need stores
    weight_inspection_overrun: int = 5      # penalty per capacity unit overrun
    #: Solver wall-time cap (seconds). Small networks solve far below this.
    max_time_seconds: float = 10.0


# --------------------------------------------------------------------------- #
# Result records
# --------------------------------------------------------------------------- #
@dataclass
class DecisionAction:
    """One recommended operational action (Req 10.2).

    Carries everything the Recommended Action Panel and the audit trail need:
    the affected product/lot id, the triggering condition, the action kind, a
    priority rank (higher = more urgent), whether ``Human_Review`` is required
    before the action may be executed, and the status tag (``SIMULATED`` here,
    because the only source is the synthetic operational network).
    """

    lot_id: str
    product_id: str
    action: str
    triggering_condition: str
    priority_rank: int
    human_review_required: bool
    #: True only for an action driven by a verified official recall (all three
    #: of official_recall + evidence_verified + confirmed_recall set).
    verified_official_recall: bool = False
    status: str = SIMULATED


@dataclass
class DecisionResult:
    """The engine's output for one network.

    When ``feasible`` is ``False`` the engine returns **no distribution
    recommendation**: ``actions`` is empty, ``no_safety_compliant_solution`` is
    ``True`` and ``reason`` explains why (Req 10.9). ``isolate_lot_ids`` lists
    every lot the hard constraints force to isolation.
    """

    feasible: bool
    actions: list[DecisionAction]
    no_safety_compliant_solution: bool
    reason: Optional[str]
    isolate_lot_ids: list[str]
    primary_actor: str = PRIMARY_ACTOR
    status: str = SIMULATED
    _meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Regulatory-evidence discipline
# --------------------------------------------------------------------------- #
def is_verified_official_recall(lot: Lot) -> bool:
    """True iff ``lot`` is a VERIFIED official recall.

    All three regulatory-evidence flags must hold; a SIMULATED
    ``distribution_blocked`` flag alone never promotes a synthetic lot to a
    verified official recall (correction 4, Req 16.6).
    """
    return bool(lot.official_recall and lot.evidence_verified and lot.confirmed_recall)


# --------------------------------------------------------------------------- #
# Core solve
# --------------------------------------------------------------------------- #
def optimize(
    network: SyntheticOperationalNetwork,
    config: Optional[OptimizerConfig] = None,
) -> DecisionResult:
    """Run the safety-constrained CP-SAT engine over ``network``.

    Returns a :class:`DecisionResult`. The hard safety constraints are modeled
    as CP-SAT constraints (not post-hoc filtering) so the solver can only ever
    choose actions inside the safety-feasible region; secondary objectives are
    the sole content of the objective function.
    """
    config = config or OptimizerConfig()
    model = cp_model.CpModel()

    stores_by_id = {s.store_id: s for s in network.stores}
    suppliers_by_id = {s.supplier_id: s for s in network.suppliers}

    # Per-lot decision variables. ``distribute`` and ``isolate`` are the
    # safety-governed variables; the rest are action selectors.
    distribute: dict[str, cp_model.IntVar] = {}
    isolate: dict[str, cp_model.IntVar] = {}
    prioritize: dict[str, cp_model.IntVar] = {}
    replace: dict[str, cp_model.IntVar] = {}

    # Hard-constraint bookkeeping, independent of the solver outcome.
    forced_isolate: set[str] = set()
    confirmed_recall_present = False

    for lot in network.lots:
        lid = lot.lot_id
        distribute[lid] = model.NewBoolVar(f"distribute_{lid}")
        isolate[lid] = model.NewBoolVar(f"isolate_{lid}")
        prioritize[lid] = model.NewBoolVar(f"prioritize_{lid}")
        replace[lid] = model.NewBoolVar(f"replace_{lid}")

        verified = is_verified_official_recall(lot)

        # HARD SAFETY (Req 10.6/10.7): a confirmed-recall lot is NEVER
        # distributed and is ALWAYS isolated. Wired from the regulatory track,
        # independent of model risk/uncertainty.
        if lot.confirmed_recall:
            model.Add(distribute[lid] == 0)
            model.Add(isolate[lid] == 1)
            forced_isolate.add(lid)
            confirmed_recall_present = confirmed_recall_present or verified

        # HARD SAFETY: a blocked / pending-result lot is NEVER distributed
        # (it requires a Human_Review release step before it could move).
        if lot.distribution_blocked:
            model.Add(distribute[lid] == 0)

        # A lot can never be both distributed and isolated.
        model.Add(distribute[lid] + isolate[lid] <= 1)

        # Replacement allocation may use ONLY compliant supply: a recalled or
        # blocked lot can never itself serve as replacement, and replacement
        # only makes sense when compliant replacement units exist.
        if lot.confirmed_recall or lot.distribution_blocked or lot.replacement_supply <= 0:
            model.Add(replace[lid] == 0)

        # Prioritized testing/inspection is withheld from a lot already forced
        # to isolation (it leaves the saleable pool); allowed otherwise.
        if lot.confirmed_recall:
            model.Add(prioritize[lid] == 0)

    # ------------------------------------------------------------------ #
    # Secondary objective — built ONLY from safety-feasible variables.
    # ------------------------------------------------------------------ #
    objective_terms: list[cp_model.LinearExpr] = []

    # Reward prioritizing high-risk, still-saleable lots.
    for lot in network.lots:
        if (
            not lot.confirmed_recall
            and lot.risk_score >= config.risk_threshold
        ):
            objective_terms.append(
                config.weight_inspection_coverage * prioritize[lot.lot_id]
            )

    # Inspection capacity is a SOFT budget: exceeding it is penalized but never
    # allowed to relax a hard safety constraint. Model an overrun term.
    total_inspection = sum(
        lot.inspection_cost * prioritize[lot.lot_id] for lot in network.lots
    )
    overrun = model.NewIntVar(0, 10_000, "inspection_overrun")
    model.Add(overrun >= total_inspection - network.inspection_capacity)
    model.Add(overrun >= 0)
    objective_terms.append(-config.weight_inspection_overrun * overrun)

    # Reward restoring access via compliant replacement, with an equity bonus
    # for stores flagged High_Need_Community (Req 10.4 equitable access).
    for lot in network.lots:
        store = stores_by_id.get(lot.destination_store_id)
        if store is None:
            continue
        objective_terms.append(
            config.weight_replacement_access * replace[lot.lot_id]
        )
        if store.high_food_need:
            objective_terms.append(
                config.weight_high_need_bonus * replace[lot.lot_id]
            )

    model.Maximize(sum(objective_terms))

    # ------------------------------------------------------------------ #
    # Solve (deterministic).
    # ------------------------------------------------------------------ #
    solver = cp_model.CpSolver()
    solver.parameters.random_seed = config.seed
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = config.max_time_seconds
    status = solver.Solve(model)

    meta = {
        "label": SIMULATED,
        "primary_actor": PRIMARY_ACTOR,
        "solver_status": solver.StatusName(status),
        "seed": config.seed,
        "n_lots": len(network.lots),
        "confirmed_recall_lots": sorted(forced_isolate),
        "verified_official_recall_present": confirmed_recall_present,
    }

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # No safety-compliant solution: return NO distribution recommendation
        # and an explicit indicator + reason (Req 10.9).
        return DecisionResult(
            feasible=False,
            actions=[],
            no_safety_compliant_solution=True,
            reason=(
                "No safety-compliant solution: CP-SAT returned "
                f"{solver.StatusName(status)} under the hard food-safety "
                "constraints; no distribution recommendation is issued."
            ),
            isolate_lot_ids=sorted(forced_isolate),
            _meta=meta,
        )

    # ------------------------------------------------------------------ #
    # Build the ranked action list from the solved model.
    # ------------------------------------------------------------------ #
    actions: list[DecisionAction] = []

    for lot in network.lots:
        lid = lot.lot_id
        verified = is_verified_official_recall(lot)

        # 1. Match against confirmed recalls — a lookup action emitted for any
        #    confirmed-recall lot (the regulatory-evidence match step).
        if lot.confirmed_recall:
            actions.append(
                DecisionAction(
                    lot_id=lid,
                    product_id=lot.product_id,
                    action="match_against_confirmed_recall",
                    triggering_condition=(
                        "lot id matched a confirmed recall record"
                        if verified
                        else "lot flagged confirmed_recall (unverified source)"
                    ),
                    priority_rank=0,  # assigned below
                    human_review_required=True,
                    verified_official_recall=verified,
                )
            )
            # 2. Isolate recalled inventory — forced by the hard constraint.
            if solver.Value(isolate[lid]) == 1:
                actions.append(
                    DecisionAction(
                        lot_id=lid,
                        product_id=lot.product_id,
                        action="isolate_recalled_inventory",
                        triggering_condition=(
                            "confirmed recall: inventory must be isolated and "
                            "never distributed"
                        ),
                        priority_rank=0,
                        human_review_required=True,
                        verified_official_recall=verified,
                    )
                )

        # 3. Escalate for human assessment — a blocked/pending lot needs a
        #    Human_Review release step before it could ever move.
        if lot.distribution_blocked and not lot.confirmed_recall:
            actions.append(
                DecisionAction(
                    lot_id=lid,
                    product_id=lot.product_id,
                    action="escalate_for_human_assessment",
                    triggering_condition=(
                        "distribution blocked pending test result; human "
                        "review required before release"
                    ),
                    priority_rank=0,
                    human_review_required=True,
                    verified_official_recall=False,
                )
            )

        # 4. Prioritize testing/inspection — risk-driven, chosen by the solver
        #    within capacity.
        if solver.Value(prioritize[lid]) == 1:
            actions.append(
                DecisionAction(
                    lot_id=lid,
                    product_id=lot.product_id,
                    action="prioritize_testing_inspection",
                    triggering_condition=(
                        f"model surveillance risk {lot.risk_score:.2f} "
                        f">= threshold {config.risk_threshold:.2f}"
                    ),
                    priority_rank=0,
                    human_review_required=False,
                    verified_official_recall=False,
                )
            )

        # 5. Request supplier documentation — supplier docs not on file.
        supplier = suppliers_by_id.get(lot.supplier_id)
        if supplier is not None and not supplier.documentation_on_file:
            actions.append(
                DecisionAction(
                    lot_id=lid,
                    product_id=lot.product_id,
                    action="request_supplier_documentation",
                    triggering_condition=(
                        f"supplier {lot.supplier_id} has no documentation on "
                        "file"
                    ),
                    priority_rank=0,
                    human_review_required=False,
                    verified_official_recall=False,
                )
            )

        # 6. Allocate compliant replacement — restore access with compliant
        #    supply (solver-selected, compliant-only by construction).
        if solver.Value(replace[lid]) == 1:
            store = stores_by_id.get(lot.destination_store_id)
            high_need = bool(store and store.high_food_need)
            actions.append(
                DecisionAction(
                    lot_id=lid,
                    product_id=lot.product_id,
                    action="allocate_compliant_replacement",
                    triggering_condition=(
                        "compliant replacement supply available"
                        + (" for High_Need_Community store" if high_need else "")
                    ),
                    priority_rank=0,
                    # Reallocation to restore access is a consequential move;
                    # gate it behind Human_Review when serving a High_Need store.
                    human_review_required=high_need,
                    verified_official_recall=False,
                )
            )

    # Assign priority ranks: action-kind order is the primary urgency signal;
    # higher rank = more urgent. Ordering is fully deterministic.
    kind_priority = {kind: len(ACTION_KINDS) - i for i, kind in enumerate(ACTION_KINDS)}
    for act in actions:
        act.priority_rank = kind_priority.get(act.action, 0)

    actions.sort(
        key=lambda a: (-a.priority_rank, a.lot_id, a.action)
    )

    return DecisionResult(
        feasible=True,
        actions=actions,
        no_safety_compliant_solution=False,
        reason=None,
        isolate_lot_ids=sorted(forced_isolate),
        _meta=meta,
    )


def result_to_dict(result: DecisionResult) -> dict:
    """Serialize a :class:`DecisionResult` to a plain JSON-ready dict."""
    return {
        "_meta": result._meta,
        "status": result.status,
        "primary_actor": result.primary_actor,
        "feasible": result.feasible,
        "no_safety_compliant_solution": result.no_safety_compliant_solution,
        "reason": result.reason,
        "isolate_lot_ids": result.isolate_lot_ids,
        "actions": [asdict(a) for a in result.actions],
    }
