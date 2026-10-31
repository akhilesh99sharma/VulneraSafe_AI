"""Three decision scenarios + policy comparison artifact emitter (Task 4.6).

This module assembles the three required scenarios on top of the seeded
:mod:`src.decision.synth_network` and the policy engine in
:mod:`src.decision.policies`, runs all three policies (A/B/C) on IDENTICAL
inputs for each scenario, and emits a concise comparison **JSON** and **CSV**
suitable for static React consumption.

The three scenarios (Req 11.2)
------------------------------
1. ``listeria_rte_recall`` — a Listeria RTE **verified-evidence recall**
   response. One lot is promoted to a confirmed recall and must be isolated
   (hard safety), and compliant replacement supply is available to restore
   access. Because this environment has **no live official FSIS recall record**
   (the Recalls/PHA feed is firewalled per the scientific audit), the recall is
   labeled a **SIMULATED verified-evidence scenario** — never presented as a
   live regulatory alert.
2. ``salmonella_poultry_limited_inspection`` — an elevated Salmonella
   raw-poultry surveillance concern under a **limited testing/inspection
   budget** (inspection capacity tightened). No confirmed recall or block; the
   hazard is a surveillance signal, so the retrospective positive-test-capture
   metric is reported not-valid for this scenario (Req 11.5).
3. ``stec_beef_high_need`` — a STEC raw-beef concern with **constrained
   compliant inventory** and ``High_Need_Community`` needs.

Hazard vs vulnerability, and what is SIMULATED
----------------------------------------------
Scenario *hazard* is connected to the real saved model predictions through
:func:`src.decision.policies.load_risk_evidence` (policies B/C). Scenario
*vulnerability / food-access* context is connected to the real ACS / Food Access
Atlas static fields through :func:`src.decision.policies.load_food_access_context`
and is used only for policy C allocation weighting. The operational network and
every operational outcome stay SIMULATED. No observed illness reduction is ever
produced.

Determinism
-----------
Each scenario is built from a fixed per-scenario seed, so the whole artifact is
reproducible: identical inputs yield byte-identical JSON/CSV.

Validates: Requirements 11.1-11.7, 16.6 (verified evidence vs live alert).
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from dataclasses import replace as dc_replace

from src.decision.policies import (
    METRIC_NAMES,
    POLICIES,
    PolicyResult,
    RiskEvidence,
    evaluate_all_policies,
    load_food_access_context,
    load_risk_evidence,
)
from src.decision.synth_network import (
    PRIMARY_ACTOR,
    SIMULATED,
    NetworkConfig,
    SyntheticOperationalNetwork,
    generate_network,
)

__all__ = [
    "SCENARIO_IDS",
    "ScenarioSpec",
    "SCENARIOS",
    "build_scenario_network",
    "run_scenario",
    "run_all_scenarios",
    "scenario_comparison_dict",
    "write_comparison_artifacts",
    "build_and_write",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
#: Scenario artifacts are a Python->web bridge, so they go under the web data dir.
WEB_DATA_DIR = REPO_ROOT / "web" / "public" / "data"
#: A mirror copy under data/synthetic keeps the full SIMULATED result together
#: with the other isolated synthetic outputs.
SYNTHETIC_DIR = REPO_ROOT / "data" / "synthetic"

ARTIFACT_VERSION = "0.1.0"


# --------------------------------------------------------------------------- #
# Scenario specification
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ScenarioSpec:
    """A declarative description of one scenario.

    The spec is turned into a concrete (SIMULATED) network by
    :func:`build_scenario_network`, which tightens capacity / inventory and
    promotes the designated lot(s) to the scenario's hazard state while keeping
    everything else from the seeded base network.
    """

    scenario_id: str
    pathogen: str
    commodity: str
    title: str
    description: str
    seed: int
    #: Number of lots forced to the scenario's focal pathogen.
    focal_lots: int
    #: Promote one focal lot to a (SIMULATED) verified confirmed recall.
    verified_recall: bool
    #: Scale factor applied to inspection capacity (<1 tightens the budget).
    inspection_capacity_scale: float
    #: Scale factor applied to compliant replacement supply (<1 constrains it).
    replacement_supply_scale: float
    #: Force at least this many destination stores to High_Need_Community.
    min_high_need_stores: int
    #: Whether the recall is a live official record (always False here).
    live_official_recall: bool = False


SCENARIO_IDS: tuple[str, ...] = (
    "listeria_rte_recall",
    "salmonella_poultry_limited_inspection",
    "stec_beef_high_need",
)

SCENARIOS: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        scenario_id="listeria_rte_recall",
        pathogen="Listeria",
        commodity="rte",
        title="Listeria RTE verified-evidence recall + replacement allocation",
        description=(
            "A ready-to-eat product lot is under a verified-evidence recall and "
            "must be isolated (hard safety constraint); compliant replacement "
            "supply is allocated to restore access. SIMULATED verified-evidence "
            "scenario: no live official FSIS recall record exists in this "
            "environment (Recalls/PHA feed firewalled), so this is NOT presented "
            "as a live regulatory alert."
        ),
        seed=4601,
        focal_lots=8,
        verified_recall=True,
        inspection_capacity_scale=1.0,
        replacement_supply_scale=1.0,
        min_high_need_stores=2,
    ),
    ScenarioSpec(
        scenario_id="salmonella_poultry_limited_inspection",
        pathogen="Salmonella",
        commodity="raw_poultry",
        title="Elevated Salmonella raw-poultry signal under limited inspection",
        description=(
            "An elevated Salmonella raw-poultry surveillance signal arrives with "
            "a tightened testing/inspection budget. Policies differ in how they "
            "spend the limited budget; safety constraints are unchanged. There is "
            "no confirmed recall or block in this scenario, so retrospective "
            "positive-test capture is reported as not-valid (Req 11.5)."
        ),
        seed=4602,
        focal_lots=12,
        verified_recall=False,
        inspection_capacity_scale=0.4,
        replacement_supply_scale=1.0,
        min_high_need_stores=2,
    ),
    ScenarioSpec(
        scenario_id="stec_beef_high_need",
        pathogen="STEC",
        commodity="raw_beef",
        title="STEC raw-beef concern, constrained supply, High_Need_Community",
        description=(
            "A STEC raw-beef concern with constrained compliant replacement "
            "inventory serving High_Need_Community stores. Policy C's food-access "
            "weighting is exercised here; safety still dominates access."
        ),
        seed=4603,
        focal_lots=10,
        verified_recall=False,
        inspection_capacity_scale=0.6,
        replacement_supply_scale=0.4,
        min_high_need_stores=4,
    ),
)


# --------------------------------------------------------------------------- #
# Scenario network construction (deterministic, SIMULATED)
# --------------------------------------------------------------------------- #
def build_scenario_network(spec: ScenarioSpec) -> SyntheticOperationalNetwork:
    """Build the concrete SIMULATED network for ``spec`` deterministically.

    Starts from a seeded base network, then shapes it to the scenario:
    * clears every lot's residual synthetic ``distribution_blocked`` flag so the
      scenario's hazard state is the ONLY intentional safety input and every
      policy sees identical, deliberate inputs;
    * forces ``focal_lots`` lots to the scenario pathogen/commodity;
    * for a verified-recall scenario, promotes the first focal lot to a
      confirmed, evidence-verified, official (but SIMULATED) recall and ensures
      it has compliant replacement supply;
    * tightens inspection capacity and/or replacement supply per the scale
      factors;
    * guarantees at least ``min_high_need_stores`` High_Need_Community stores.
    The SAME returned network object is handed to every policy (identical inputs).
    """
    base = generate_network(NetworkConfig(seed=spec.seed))

    # Ensure enough High_Need_Community stores.
    stores = [dc_replace(s) for s in base.stores]
    high_need_count = sum(1 for s in stores if s.high_food_need)
    i = 0
    while high_need_count < spec.min_high_need_stores and i < len(stores):
        if not stores[i].high_food_need:
            stores[i] = dc_replace(stores[i], high_food_need=True,
                                   low_food_access=True)
            high_need_count += 1
        i += 1
    high_need_ids = [s.store_id for s in stores if s.high_food_need]

    # Shape the lots: clear residual synthetic block flags, assign focal
    # pathogen, scale replacement supply, and set the scenario hazard state.
    lots = []
    focal_assigned = 0
    for idx, lot in enumerate(base.lots):
        # Clear any synthetic block flag on EVERY lot: the scenario is the only
        # source of a safety state, so inputs are deliberate and identical.
        new_lot = dc_replace(
            lot,
            distribution_blocked=False,
            confirmed_recall=False,
            official_recall=False,
            evidence_verified=False,
        )
        if focal_assigned < spec.focal_lots:
            new_replacement = int(round(lot.replacement_supply
                                        * spec.replacement_supply_scale))
            # STEC scenario routes focal lots to High_Need stores to exercise
            # the access-aware policy; done deterministically by index.
            dest = new_lot.destination_store_id
            if spec.scenario_id == "stec_beef_high_need" and high_need_ids:
                dest = high_need_ids[focal_assigned % len(high_need_ids)]
            new_lot = dc_replace(
                new_lot,
                pathogen=spec.pathogen,
                commodity=spec.commodity,
                replacement_supply=max(0, new_replacement),
                destination_store_id=dest,
            )
            # Promote the FIRST focal lot to a verified (SIMULATED) recall.
            if spec.verified_recall and focal_assigned == 0:
                new_lot = dc_replace(
                    new_lot,
                    confirmed_recall=True,
                    official_recall=True,
                    evidence_verified=True,
                    distribution_blocked=True,
                    # Guarantee compliant replacement supply exists to allocate.
                    replacement_supply=max(new_lot.replacement_supply,
                                           max(1, new_lot.inventory_quantity // 2)),
                )
            focal_assigned += 1
        lots.append(new_lot)

    inspection_capacity = max(
        1, int(round(base.inspection_capacity * spec.inspection_capacity_scale))
    )

    net = SyntheticOperationalNetwork(
        suppliers=[dc_replace(s) for s in base.suppliers],
        stores=stores,
        lots=lots,
        inspection_capacity=inspection_capacity,
        config=base.config,
        _meta=dict(base._meta),
    )
    net._meta = {
        **base._meta,
        "scenario_id": spec.scenario_id,
        "scenario_title": spec.title,
        "verified_recall": spec.verified_recall,
        "live_official_recall": spec.live_official_recall,
        "recall_labeling_note": (
            "SIMULATED verified-evidence recall; NOT a live official regulatory "
            "alert (no live FSIS recall record available in this environment)."
            if spec.verified_recall
            else "No recall in this scenario."
        ),
        "inspection_capacity": inspection_capacity,
        "high_need_store_ids": high_need_ids,
    }
    return net


# --------------------------------------------------------------------------- #
# Scenario run
# --------------------------------------------------------------------------- #
@dataclass
class ScenarioRun:
    """All three policy results for one scenario, plus its provenance."""

    spec: ScenarioSpec
    network: SyntheticOperationalNetwork
    policy_results: list[PolicyResult]
    food_access_context_available: bool
    status: str = SIMULATED
    _meta: dict = field(default_factory=dict)


def run_scenario(spec: ScenarioSpec) -> ScenarioRun:
    """Build and evaluate one scenario across policies A/B/C on identical inputs."""
    network = build_scenario_network(spec)
    evidence = load_risk_evidence(spec.pathogen)
    fa_context = load_food_access_context(spec.pathogen)

    results = evaluate_all_policies(spec.scenario_id, network, evidence)

    meta = {
        "label": SIMULATED,
        "scenario_id": spec.scenario_id,
        "pathogen": spec.pathogen,
        "risk_evidence_source": evidence.source_path,
        "risk_evidence_available": evidence.available,
        "food_access_context_available": bool(fa_context),
        "food_access_context_source": (
            "ACS + Food Access Atlas static fields on harmonized model table"
            if fa_context else "unavailable (synthetic store flags used; recorded)"
        ),
        "verified_recall": spec.verified_recall,
        "live_official_recall": spec.live_official_recall,
    }
    return ScenarioRun(
        spec=spec,
        network=network,
        policy_results=results,
        food_access_context_available=bool(fa_context),
        _meta=meta,
    )


def run_all_scenarios() -> list[ScenarioRun]:
    """Run all three scenarios deterministically."""
    return [run_scenario(spec) for spec in SCENARIOS]


# --------------------------------------------------------------------------- #
# Artifact serialization
# --------------------------------------------------------------------------- #
def scenario_comparison_dict(runs: list[ScenarioRun]) -> dict:
    """Assemble the concise comparison dict (React-friendly, fully labeled)."""
    scenarios_out = []
    for run in runs:
        policies_out = []
        for pr in run.policy_results:
            policies_out.append(
                {
                    "policy": pr.policy,
                    "status": pr.status,
                    "feasible": pr.decision.feasible,
                    "no_safety_compliant_solution": pr.decision.no_safety_compliant_solution,
                    "isolate_lot_ids": pr.decision.isolate_lot_ids,
                    "human_review_required_actions": pr.human_review_required_actions,
                    "risk_evidence": pr._meta.get("risk_evidence"),
                    "policy_config": pr._meta.get("policy_config"),
                    "metrics": [
                        {
                            "metric": m.metric,
                            "value": m.value,
                            "diff_vs_a": m.diff_vs_a,
                            "ci_low": m.ci_low,
                            "ci_high": m.ci_high,
                            "valid": m.valid,
                            "not_valid_reason": m.not_valid_reason,
                            "status": m.status,
                        }
                        for m in pr.metrics
                    ],
                }
            )
        scenarios_out.append(
            {
                "scenario_id": run.spec.scenario_id,
                "title": run.spec.title,
                "description": run.spec.description,
                "pathogen": run.spec.pathogen,
                "commodity": run.spec.commodity,
                "verified_recall": run.spec.verified_recall,
                "live_official_recall": run.spec.live_official_recall,
                "recall_labeling_note": run.network._meta.get("recall_labeling_note"),
                "provenance": run._meta,
                "policies": policies_out,
            }
        )

    return {
        "artifact": "scenario_results",
        "artifact_version": ARTIFACT_VERSION,
        "status": SIMULATED,
        "primary_actor": PRIMARY_ACTOR,
        "label": SIMULATED,
        "metric_names": list(METRIC_NAMES),
        "policies": list(POLICIES),
        "notes": (
            "Operational network and outcomes are SIMULATED. Hazard risk is from "
            "real saved model predictions (PREDICTED); food-access context is "
            "from real ACS / Food Access Atlas fields. Policy A is the diff-vs-A "
            "baseline. retrospective_positive_test_capture is omitted with a "
            "not-valid indicator where it cannot be validly computed (Req 11.5). "
            "High-consequence actions are gated behind Human_Review (Req 11.7). "
            "No observed illness reduction is claimed."
        ),
        "scenarios": scenarios_out,
    }


def _comparison_rows(runs: list[ScenarioRun]) -> list[dict]:
    """Flatten the comparison into one row per scenario x policy x metric."""
    rows: list[dict] = []
    for run in runs:
        for pr in run.policy_results:
            for m in pr.metrics:
                rows.append(
                    {
                        "scenario_id": run.spec.scenario_id,
                        "pathogen": run.spec.pathogen,
                        "policy": pr.policy,
                        "metric": m.metric,
                        "value": "" if m.value is None else m.value,
                        "diff_vs_a": "" if m.diff_vs_a is None else m.diff_vs_a,
                        "ci_low": "" if m.ci_low is None else m.ci_low,
                        "ci_high": "" if m.ci_high is None else m.ci_high,
                        "valid": m.valid,
                        "not_valid_reason": m.not_valid_reason or "",
                        "status": m.status,
                        "human_review_required": bool(pr.human_review_required_actions),
                    }
                )
    return rows


def _comparison_csv(runs: list[ScenarioRun]) -> str:
    """Render the flattened comparison as deterministic CSV text."""
    rows = _comparison_rows(runs)
    fieldnames = [
        "scenario_id", "pathogen", "policy", "metric", "value", "diff_vs_a",
        "ci_low", "ci_high", "valid", "not_valid_reason", "status",
        "human_review_required",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def write_comparison_artifacts(
    runs: list[ScenarioRun],
    *,
    web_data_dir: Optional[Path] = None,
    synthetic_dir: Optional[Path] = None,
) -> dict[str, Path]:
    """Write the comparison JSON and CSV to the web data dir (+ synthetic mirror).

    Returns a dict of the paths written. Serialization is deterministic so
    identical inputs produce byte-identical files.
    """
    web_dir = web_data_dir or WEB_DATA_DIR
    synth_dir = synthetic_dir or SYNTHETIC_DIR
    web_dir.mkdir(parents=True, exist_ok=True)
    synth_dir.mkdir(parents=True, exist_ok=True)

    payload = scenario_comparison_dict(runs)
    json_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    csv_text = _comparison_csv(runs)

    json_path = web_dir / "scenario_results.json"
    csv_path = web_dir / "scenario_results.csv"
    synth_json = synth_dir / "scenario_results.json"

    json_path.write_text(json_text, encoding="utf-8")
    csv_path.write_text(csv_text, encoding="utf-8")
    synth_json.write_text(json_text, encoding="utf-8")

    return {
        "json": json_path,
        "csv": csv_path,
        "synthetic_json": synth_json,
    }


def build_and_write(
    *,
    web_data_dir: Optional[Path] = None,
    synthetic_dir: Optional[Path] = None,
) -> dict[str, Path]:
    """Run all scenarios and persist the comparison artifacts in one call."""
    runs = run_all_scenarios()
    return write_comparison_artifacts(
        runs, web_data_dir=web_data_dir, synthetic_dir=synthetic_dir
    )


if __name__ == "__main__":  # pragma: no cover - manual invocation
    paths = build_and_write()
    for name, path in paths.items():
        print(f"Wrote {name} -> {path}")
