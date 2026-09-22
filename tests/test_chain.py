"""Tests for the claims the demo makes. Run with: pytest -q

These cover, in miniature, experiments E1 (replay correctness), E3 (tamper detection) and the
idempotency and concurrency behaviour of the command side.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import uuid

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


@pytest.fixture()
def app_db(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp()) / "test.db"
    monkeypatch.setenv("BAGAY_DB", f"sqlite:///{tmp}")
    for mod in [m for m in list(sys.modules) if m.startswith("backend")]:
        del sys.modules[mod]
    from backend import chain, commands, db, projector           # imported after the env var
    db.DB_URL = f"sqlite:///{tmp}"
    db.IS_PG = False
    db.init_db(reset=True)
    conn = db.connect()
    db.set_immutability(conn, True)
    return type("Ctx", (), {"conn": conn, "chain": chain, "commands": commands,
                            "db": db, "projector": projector})


def seed_small(ctx, n_assets=6):
    for i in range(n_assets):
        aid = f"BGY-0000000000-SL-{i:05d}"
        ctx.commands.register_asset(ctx.conn, asset_id=aid, name=f"Streetlight {i}",
                                    category="SL", purok="Purok 1", acquisition_cost=18500)
        ctx.commands.record_inspection(ctx.conn, asset_id=aid, condition="POOR")
        wo = ctx.commands.open_work_order(ctx.conn, asset_id=aid, priority="P2")
        wo_id = __import__("json").loads(wo["payload"])["work_order_id"]
        ctx.commands.start_repair(ctx.conn, asset_id=aid, work_order_id=wo_id)
        ctx.commands.complete_repair(ctx.conn, asset_id=aid, work_order_id=wo_id, actual_cost=1200)
    ctx.projector.rebuild_all(ctx.conn)


def test_clean_log_verifies(app_db):
    seed_small(app_db)
    app_db.chain.create_checkpoint(app_db.conn)
    report = app_db.chain.verify(app_db.conn)
    assert report["ok"], report["findings"]
    assert report["events_checked"] == app_db.chain.head(app_db.conn)["position"]


def test_hash_is_deterministic(app_db):
    """Recomputing every hash from stored content must reproduce what was stored."""
    seed_small(app_db, 3)
    for row in app_db.conn.query("SELECT * FROM es_events ORDER BY global_position"):
        again = app_db.chain.compute_hash(row["prev_hash"], row["stream_prev_hash"],
                                          row["global_position"], app_db.chain.envelope_of(row))
        assert again == row["event_hash"]


def test_append_is_idempotent(app_db):
    seed_small(app_db, 1)
    cid = str(uuid.uuid4())
    a = app_db.commands.record_inspection(app_db.conn, asset_id="BGY-0000000000-SL-00000",
                                          condition="GOOD", command_id=cid)
    b = app_db.commands.record_inspection(app_db.conn, asset_id="BGY-0000000000-SL-00000",
                                          condition="GOOD", command_id=cid)
    assert b["duplicate"] and a["global_position"] == b["global_position"]


def test_stale_version_conflicts(app_db):
    seed_small(app_db, 1)
    with pytest.raises(app_db.chain.Conflict):
        app_db.commands.record_inspection(app_db.conn, asset_id="BGY-0000000000-SL-00000",
                                          condition="GOOD", expected_version=1)


def test_lifecycle_rejects_impossible_transition(app_db):
    seed_small(app_db, 1)
    with pytest.raises(app_db.commands.Denied):        # nothing is under repair right now
        app_db.commands.complete_repair(app_db.conn, asset_id="BGY-0000000000-SL-00000",
                                        work_order_id=str(uuid.uuid4()))


def test_role_rights_enforced(app_db):
    seed_small(app_db, 1)
    with pytest.raises(app_db.commands.Denied):        # a resident cannot attest an inspection
        app_db.commands.submit(app_db.conn, asset_id="BGY-0000000000-SL-00000",
                               event_type="InspectionRecorded", payload={"condition": "GOOD"},
                               actor_role="PUBLIC")


def test_database_blocks_updates_and_deletes(app_db):
    seed_small(app_db, 1)
    for sql in ("UPDATE es_events SET payload = '{}' WHERE global_position = 2",
                "DELETE FROM es_events WHERE global_position = 2"):
        with pytest.raises(Exception):
            app_db.conn.execute(sql)


def test_rebuild_matches_incremental(app_db):
    """E1 in miniature: replaying the log must produce the same read models."""
    seed_small(app_db, 5)
    before = app_db.conn.query("SELECT * FROM proj_asset_current ORDER BY asset_id")
    app_db.projector.rebuild_all(app_db.conn)
    after = app_db.conn.query("SELECT * FROM proj_asset_current ORDER BY asset_id")
    assert before == after and before


def test_as_of_replay(app_db):
    seed_small(app_db, 1)
    aid = "BGY-0000000000-SL-00000"
    events = app_db.chain.stream_events(app_db.conn, f"asset:{aid}")
    mid = events[1]["global_position"]                 # right after the first inspection
    past = app_db.commands.load_asset(app_db.conn, aid, as_of_position=mid)
    now = app_db.commands.load_asset(app_db.conn, aid)
    assert past["lifetime_repair_cost"] == 0 and now["lifetime_repair_cost"] == 1200
    assert past["status"] == "NEEDS_ATTENTION" and now["status"] == "IN_SERVICE"


@pytest.mark.parametrize("mode,caught_without_witness", [
    ("edit", True), ("delete", True), ("truncate", False), ("rewrite", False)])
def test_tamper_detection(app_db, mode, caught_without_witness):
    """E3 in miniature: the chain alone catches naive edits; witnesses catch the rest."""
    seed_small(app_db, 8)
    app_db.chain.create_checkpoint(app_db.conn)
    from backend import demo_tamper
    result = demo_tamper.run(app_db.conn, mode)
    assert result["without_witness"]["detected"] is caught_without_witness
    assert result["with_witness"]["detected"] is True
