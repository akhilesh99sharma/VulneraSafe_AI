"""Tests for the seeded Synthetic_Operational_Network generator (Task 4.1).

Covers the four focused guarantees the task requires:

* **Deterministic seeding** — identical ``(seed, config)`` produces an identical
  network and byte-identical JSON artifacts; a different seed differs.
* **Schema validity** — every entity carries the fields later CP-SAT and the
  three scenarios need (product/lot ids, pathogen/commodity, supplier, source
  state, destinations, inventory, replacement supply, cost, inspection capacity,
  recall/evidence flags, high-food-need / food-access context, hard-safety
  inputs).
* **Explicit synthetic labeling** — every record and the top level is tagged
  ``SIMULATED`` and nothing else; recall/evidence flags default off.
* **Physical / logical isolation** — artifacts are written only under
  ``data/synthetic/`` and no record set mixes synthetic and real data.

Validates: Requirements 4.4, 11.6 (Property 9).
"""
from __future__ import annotations

import json

from src.decision import synth_network as sn
from src.decision.synth_network import (
    PRIMARY_ACTOR,
    SIMULATED,
    NetworkConfig,
    build_and_write,
    generate_network,
    network_to_dict,
    write_network,
)

# --------------------------------------------------------------------------- #
# Deterministic seeding
# --------------------------------------------------------------------------- #
def test_same_seed_produces_identical_network():
    a = network_to_dict(generate_network(NetworkConfig(seed=7)))
    b = network_to_dict(generate_network(NetworkConfig(seed=7)))
    assert a == b


def test_same_seed_produces_identical_json_bytes(tmp_path):
    cfg = NetworkConfig(seed=7)
    p1 = write_network(generate_network(cfg), synthetic_root=tmp_path / "one")
    p2 = write_network(generate_network(cfg), synthetic_root=tmp_path / "two")
    assert p1.read_bytes() == p2.read_bytes()


def test_different_seed_changes_network():
    a = network_to_dict(generate_network(NetworkConfig(seed=1)))
    b = network_to_dict(generate_network(NetworkConfig(seed=2)))
    assert a != b


def test_default_seed_is_project_convention():
    assert NetworkConfig().seed == 42


# --------------------------------------------------------------------------- #
# Schema validity — fields CP-SAT + the three scenarios need
# --------------------------------------------------------------------------- #
def test_counts_match_config():
    cfg = NetworkConfig(seed=3, n_suppliers=4, n_stores=9, n_lots=20)
    net = generate_network(cfg)
    assert len(net.suppliers) == 4
    assert len(net.stores) == 9
    assert len(net.lots) == 20
    assert net.inspection_capacity >= 1


def test_lot_has_all_optimizer_fields():
    net = generate_network(NetworkConfig(seed=5))
    required = {
        "lot_id", "product_id", "product_name", "pathogen", "commodity",
        "supplier_id", "source_state", "destination_store_id",
        "inventory_quantity", "replacement_supply", "unit_cost", "risk_score",
        "inspection_cost", "official_recall", "evidence_verified",
        "confirmed_recall", "distribution_blocked", "status",
    }
    for lot in net.lots:
        d = lot.__dict__
        assert required.issubset(d), required - set(d)
        # pathogen/commodity pairing is consistent with the modeling spine
        assert sn.PATHOGEN_COMMODITY[lot.pathogen] == lot.commodity
        # referential integrity: supplier + store ids resolve
        assert any(s.supplier_id == lot.supplier_id for s in net.suppliers)
        assert any(s.store_id == lot.destination_store_id for s in net.stores)


def test_store_has_food_access_context():
    net = generate_network(NetworkConfig(seed=5))
    for store in net.stores:
        d = store.__dict__
        assert {"high_food_need", "low_food_access", "population_served"} <= set(d)
        assert isinstance(d["high_food_need"], bool)
        assert d["population_served"] > 0


def test_supplier_carries_documentation_and_source_state():
    net = generate_network(NetworkConfig(seed=5))
    for sup in net.suppliers:
        assert sup.source_state in sn.SOURCE_STATES
        assert isinstance(sup.documentation_on_file, bool)


def test_primary_actor_is_retail_director():
    net = generate_network()
    assert net.primary_actor == PRIMARY_ACTOR
    assert "Food Safety Operations Director" in PRIMARY_ACTOR


# --------------------------------------------------------------------------- #
# Explicit synthetic labeling
# --------------------------------------------------------------------------- #
def test_every_record_is_simulated():
    net = generate_network(NetworkConfig(seed=9))
    assert net.status == SIMULATED
    for record in (*net.suppliers, *net.stores, *net.lots):
        assert record.status == SIMULATED


def test_recall_and_evidence_flags_default_off():
    net = generate_network(NetworkConfig(seed=9))
    for lot in net.lots:
        # A synthetic lot is never a verified official recall by default.
        assert lot.official_recall is False
        assert lot.evidence_verified is False
        assert lot.confirmed_recall is False


def test_meta_block_states_simulated_and_isolated():
    net = generate_network(NetworkConfig(seed=9))
    meta = net._meta
    assert meta["label"] == SIMULATED
    assert meta["isolated"] is True
    assert meta["primary_actor"] == PRIMARY_ACTOR


# --------------------------------------------------------------------------- #
# Physical / logical isolation under data/synthetic
# --------------------------------------------------------------------------- #
def test_write_lands_under_synthetic_root(tmp_path):
    root = tmp_path / "data" / "synthetic"
    out = build_and_write(NetworkConfig(seed=11), synthetic_root=root)
    assert out.exists()
    assert root in out.parents


def test_written_json_is_all_simulated(tmp_path):
    root = tmp_path / "syn"
    out = build_and_write(NetworkConfig(seed=11), synthetic_root=root)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == SIMULATED
    for key in ("suppliers", "stores", "lots"):
        assert payload[key]  # non-empty
        for record in payload[key]:
            assert record["status"] == SIMULATED


def test_default_synthetic_root_is_isolated_dir():
    # The module's default output root must be the isolated synthetic dir,
    # never the real processed/interim/raw data locations.
    assert sn.SYNTHETIC_ROOT.name == "synthetic"
    assert sn.SYNTHETIC_ROOT.parent.name == "data"
    parts = sn.SYNTHETIC_ROOT.parts
    assert "processed" not in parts and "interim" not in parts and "raw" not in parts
