"""Seeded Synthetic_Operational_Network generator (Task 4.1).

The challenge brief supplies no real retailer shipment or inventory data, so the
``Decision_Engine`` is demonstrated against a **synthetic** retail operational
network. This module is the single source of that network. It is deliberately
self-contained: it reads **no** real observational artifact and writes **only**
to an isolated ``data/synthetic/`` directory, so no record set ever mixes
synthetic and real observational data (Req 4.4, 11.6; Property 9).

Primary actor: the Food Safety Operations Director of a regional grocery retail
chain. Every entity here (stores, lots, suppliers) is framed around that
director's operational choices for later CP-SAT optimization (Task 4.3) and the
three required scenarios (Task 4.6): a Listeria RTE recall with replacement
allocation; an elevated Salmonella signal under a limited inspection budget; and
a STEC concern with limited supply serving a High_Need_Community.

Labeling and isolation guarantees
----------------------------------
* Every generated record carries ``status == "SIMULATED"`` (the ``StatusTag``
  from the data contract). There is no code path that emits any other tag.
* ``official_recall`` defaults to ``False`` and ``evidence_verified`` defaults to
  ``False`` for every simulated lot: a synthetic lot is never treated as a
  verified official recall unless a scenario explicitly marks it so, and even
  then the record stays ``SIMULATED`` and is never promoted to the real
  regulatory-evidence track.
* Output lives only under ``data/synthetic/``; a top-level ``_meta`` block in
  every artifact restates the SIMULATED / isolated guarantee for any downstream
  reader.

Determinism
-----------
All randomness flows through a single ``numpy.random.default_rng(seed)`` with a
fixed default seed, matching the project convention (``RANDOM_STATE = 42``).
Identical ``(seed, config)`` inputs produce byte-identical JSON artifacts
(Property 10 spirit): dicts are serialized with ``json.dumps(..., indent=2,
ensure_ascii=False)`` and list order is fully determined by the generator.

This module intentionally does **not** implement the optimizer, policies, or
scenarios — only the network foundation they will consume.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from src.artifacts.schemas import STATUS_TAGS

# --------------------------------------------------------------------------- #
# Paths and constants
# --------------------------------------------------------------------------- #
#: Repo root: this file is ``src/decision/synth_network.py`` -> parents[2].
REPO_ROOT = Path(__file__).resolve().parents[2]

#: Isolated synthetic-only output directory (Req 4.4). Nothing real is written
#: here and nothing here is read by the real observational pipeline.
SYNTHETIC_ROOT = REPO_ROOT / "data" / "synthetic"

#: The one and only status tag any synthetic record may carry.
SIMULATED: str = "SIMULATED"

#: Fixed default seed, matching the project-wide ``RANDOM_STATE = 42`` convention
#: so identical inputs reproduce identical artifacts.
DEFAULT_SEED: int = 42

#: Primary actor held consistent across the platform (Req 1.2).
PRIMARY_ACTOR: str = "Food Safety Operations Director, regional grocery retail chain"

#: Pathogen -> commodity map, mirroring the modeling spine (design.md).
PATHOGEN_COMMODITY: dict[str, str] = {
    "Salmonella": "raw_poultry",
    "Listeria": "rte",
    "STEC": "raw_beef",
}

#: Establishment / source states the synthetic suppliers ship from. These are
#: plausible US state codes used only to key the synthetic network; they are
#: not drawn from any real establishment record.
SOURCE_STATES: tuple[str, ...] = ("GA", "AR", "NC", "TX", "IA", "NE", "CA", "PA")

__all__ = [
    "PRIMARY_ACTOR",
    "SIMULATED",
    "SYNTHETIC_ROOT",
    "DEFAULT_SEED",
    "NetworkConfig",
    "Supplier",
    "Store",
    "Lot",
    "SyntheticOperationalNetwork",
    "generate_network",
    "write_network",
    "build_and_write",
]


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class NetworkConfig:
    """Sizing + seed for one synthetic network.

    The defaults are small on purpose: enough entities to exercise CP-SAT and
    the three scenarios, cheap enough to regenerate deterministically in a test.
    """

    seed: int = DEFAULT_SEED
    n_suppliers: int = 6
    n_stores: int = 12
    n_lots: int = 40
    #: Fraction of stores flagged as High_Need_Community (food-access context).
    high_need_fraction: float = 0.25
    #: Fraction of lots that carry a simulated (unverified) recall flag.
    recall_fraction: float = 0.15

    def fingerprint(self) -> str:
        """Stable hash of the config, recorded in artifact ``_meta`` for audit."""
        payload = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Entity records (all SIMULATED)
# --------------------------------------------------------------------------- #
@dataclass
class Supplier:
    """A simulated supplier / source establishment."""

    supplier_id: str
    name: str
    source_state: str
    #: Whether supplier documentation is on file (feeds "request documentation").
    documentation_on_file: bool
    status: str = SIMULATED


@dataclass
class Store:
    """A simulated retail store / destination, with food-access context."""

    store_id: str
    name: str
    state: str
    #: Elevated food-security need (drives equitable-access secondary objective).
    high_food_need: bool
    #: USDA-Atlas-style low-access flag (food-access context, SIMULATED).
    low_food_access: bool
    #: Population served; used to weight service-to-High_Need_Community metrics.
    population_served: int
    status: str = SIMULATED


@dataclass
class Lot:
    """A simulated product lot: the unit CP-SAT assigns an action to.

    Carries every field later optimization needs: product/lot identity,
    pathogen/commodity, supplier + source state, destination store, quantity,
    replacement supply, unit cost, testing/inspection capacity inputs, the
    (defaulted-off) official-evidence / recall flags, and the hard-safety inputs.
    """

    lot_id: str
    product_id: str
    product_name: str
    pathogen: str
    commodity: str
    supplier_id: str
    source_state: str
    destination_store_id: str
    #: Units currently held of this lot.
    inventory_quantity: int
    #: Compliant replacement units available if this lot is isolated.
    replacement_supply: int
    #: Per-unit cost (secondary-objective input only; never a safety input).
    unit_cost: float
    #: Model-estimated surveillance-risk score in [0, 1] (SIMULATED stand-in).
    risk_score: float
    #: Inspection effort (capacity units) to prioritize-test this lot.
    inspection_cost: int
    #: True only when a scenario promotes this lot to a verified official recall.
    #: Defaults False: a synthetic lot is NOT an official recall by default.
    official_recall: bool = False
    #: Whether supporting evidence is verified official (vs model/simulated).
    #: Defaults False so nothing is mistaken for verified regulatory evidence.
    evidence_verified: bool = False
    #: HARD-SAFETY input: a confirmed recall lot must never be distributed and
    #: must be isolated (Req 10.6/10.7). Defaults False for a plain synthetic lot.
    confirmed_recall: bool = False
    #: HARD-SAFETY input: lot is blocked from distribution pending test result.
    distribution_blocked: bool = False
    status: str = SIMULATED


@dataclass
class SyntheticOperationalNetwork:
    """The whole generated network plus the capacity inputs CP-SAT consumes."""

    suppliers: list[Supplier]
    stores: list[Store]
    lots: list[Lot]
    #: Total inspection/testing capacity available this period (limited-budget
    #: scenarios tighten this). A capacity input, never a safety relaxation.
    inspection_capacity: int
    config: NetworkConfig
    primary_actor: str = PRIMARY_ACTOR
    status: str = SIMULATED
    _meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
def generate_network(config: Optional[NetworkConfig] = None) -> SyntheticOperationalNetwork:
    """Build a deterministic synthetic operational network.

    Pure and side-effect free: no files are read or written. Identical
    ``config`` (same seed + sizing) yields an identical network.
    """
    config = config or NetworkConfig()
    rng = np.random.default_rng(config.seed)
    pathogens = tuple(PATHOGEN_COMMODITY.keys())

    # Suppliers ------------------------------------------------------------- #
    suppliers: list[Supplier] = []
    for i in range(config.n_suppliers):
        state = SOURCE_STATES[int(rng.integers(0, len(SOURCE_STATES)))]
        suppliers.append(
            Supplier(
                supplier_id=f"SUP-{i:03d}",
                name=f"Simulated Supplier {i:03d}",
                source_state=state,
                documentation_on_file=bool(rng.random() < 0.7),
            )
        )

    # Stores ---------------------------------------------------------------- #
    stores: list[Store] = []
    for i in range(config.n_stores):
        state = SOURCE_STATES[int(rng.integers(0, len(SOURCE_STATES)))]
        high_need = bool(rng.random() < config.high_need_fraction)
        stores.append(
            Store(
                store_id=f"STORE-{i:03d}",
                name=f"Simulated Store {i:03d}",
                state=state,
                high_food_need=high_need,
                # High-need stores are more likely to also be low-access.
                low_food_access=bool(rng.random() < (0.6 if high_need else 0.2)),
                population_served=int(rng.integers(2_000, 50_000)),
            )
        )

    # Lots ------------------------------------------------------------------ #
    lots: list[Lot] = []
    for i in range(config.n_lots):
        pathogen = pathogens[int(rng.integers(0, len(pathogens)))]
        commodity = PATHOGEN_COMMODITY[pathogen]
        supplier = suppliers[int(rng.integers(0, len(suppliers)))]
        store = stores[int(rng.integers(0, len(stores)))]
        inventory = int(rng.integers(50, 1_000))
        # A simulated (unverified) recall flag on a fraction of lots. This is a
        # SIMULATED signal only: official_recall / confirmed_recall stay False.
        simulated_recall_flag = bool(rng.random() < config.recall_fraction)
        lots.append(
            Lot(
                lot_id=f"LOT-{i:04d}",
                product_id=f"PROD-{int(rng.integers(0, 200)):04d}",
                product_name=f"Simulated {commodity} product {i:04d}",
                pathogen=pathogen,
                commodity=commodity,
                supplier_id=supplier.supplier_id,
                source_state=supplier.source_state,
                destination_store_id=store.store_id,
                inventory_quantity=inventory,
                replacement_supply=int(rng.integers(0, inventory + 1)),
                unit_cost=round(float(rng.uniform(1.0, 25.0)), 2),
                risk_score=round(float(rng.random()), 4),
                inspection_cost=int(rng.integers(1, 6)),
                # Defaults below are the safe baseline; scenarios may set them.
                official_recall=False,
                evidence_verified=False,
                confirmed_recall=False,
                distribution_blocked=simulated_recall_flag,
            )
        )

    inspection_capacity = int(max(1, round(config.n_lots * 0.4)))

    network = SyntheticOperationalNetwork(
        suppliers=suppliers,
        stores=stores,
        lots=lots,
        inspection_capacity=inspection_capacity,
        config=config,
    )
    network._meta = _build_meta(config, network)
    return network


def _build_meta(config: NetworkConfig, network: SyntheticOperationalNetwork) -> dict:
    """Restate the SIMULATED / isolation guarantee inside every artifact."""
    return {
        "label": SIMULATED,
        "isolated": True,
        "isolation_note": (
            "Synthetic operational network. Contains NO real observational "
            "records and is written only under data/synthetic/. Not for the "
            "regulatory-evidence track."
        ),
        "primary_actor": PRIMARY_ACTOR,
        "seed": config.seed,
        "config_fingerprint": config.fingerprint(),
        "counts": {
            "suppliers": len(network.suppliers),
            "stores": len(network.stores),
            "lots": len(network.lots),
        },
    }


# --------------------------------------------------------------------------- #
# Serialization + isolated write
# --------------------------------------------------------------------------- #
def network_to_dict(network: SyntheticOperationalNetwork) -> dict:
    """Serialize the network to a plain, deterministic, JSON-ready dict."""
    return {
        "_meta": network._meta,
        "status": network.status,
        "primary_actor": network.primary_actor,
        "inspection_capacity": network.inspection_capacity,
        "config": asdict(network.config),
        "suppliers": [asdict(s) for s in network.suppliers],
        "stores": [asdict(s) for s in network.stores],
        "lots": [asdict(lot) for lot in network.lots],
    }


def _assert_all_simulated(payload: dict) -> None:
    """Guard: every entity record and the top level must be SIMULATED.

    A programming error that let a non-SIMULATED record through would silently
    break the isolation guarantee, so this is a hard invariant, not a test-only
    check.
    """
    if payload.get("status") != SIMULATED:
        raise ValueError("network status must be SIMULATED")
    for key in ("suppliers", "stores", "lots"):
        for record in payload[key]:
            tag = record.get("status")
            if tag != SIMULATED:
                raise ValueError(f"{key} record carries non-SIMULATED tag: {tag!r}")
            if tag not in STATUS_TAGS:
                raise ValueError(f"{key} record carries unknown status tag: {tag!r}")
    # No synthetic lot may claim to be a verified official recall by default.
    for lot in payload["lots"]:
        if lot.get("official_recall") and not lot.get("evidence_verified"):
            raise ValueError("official_recall set without evidence_verified")


def write_network(
    network: SyntheticOperationalNetwork,
    *,
    synthetic_root: Optional[Path] = None,
) -> Path:
    """Write the network to an isolated JSON artifact under ``data/synthetic/``.

    Returns the path written. Serialization is deterministic so identical inputs
    produce byte-identical files.
    """
    root = synthetic_root or SYNTHETIC_ROOT
    root.mkdir(parents=True, exist_ok=True)
    payload = network_to_dict(network)
    _assert_all_simulated(payload)
    out = root / "operational_network.json"
    out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out


def build_and_write(
    config: Optional[NetworkConfig] = None,
    *,
    synthetic_root: Optional[Path] = None,
) -> Path:
    """Generate and persist the synthetic network in one call."""
    network = generate_network(config)
    return write_network(network, synthetic_root=synthetic_root)


if __name__ == "__main__":  # pragma: no cover - manual invocation
    path = build_and_write()
    print(f"Wrote SIMULATED synthetic operational network -> {path}")
