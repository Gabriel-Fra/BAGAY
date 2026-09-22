"""Command side: validate an intention against the asset's own history, then append.

The command side never reads projections to make a decision. It rebuilds the target
stream from the log, checks the lifecycle and the caller's role, and appends.
"""
from __future__ import annotations

import uuid

from . import catalog, chain, db

ROLE_RIGHTS = {
    "PUBLIC":           {"IssueReported"},
    "FIELD_WORKER":     {"InspectionRecorded", "DamageRecorded", "RepairStarted", "RepairCompleted"},
    "SECRETARY":        {"AssetRegistered", "CustodyAssigned", "CustodyTransferred", "IssueTriaged",
                         "WorkOrderOpened", "EntryCorrected", "InspectionRecorded", "DamageRecorded"},
    "TREASURER":        {"RepairCompleted", "EntryCorrected"},
    "KAGAWAD":          {"InspectionRecorded", "DamageRecorded", "HazardDeclared", "WorkOrderOpened"},
    "PUNONG_BARANGAY":  {"AssetDeclaredUnserviceable", "AssetDisposed", "TurnoverSealed",
                         "UserEnrolled", "UserDeactivated", "HazardDeclared", "WorkOrderOpened"},
    "VERIFIER":         set(),
    "ADMIN":            set(),
    "SYSTEM":           set(catalog.EVENTS),
}


class Denied(Exception):
    pass


def asset_stream(asset_id: str) -> str:
    return f"asset:{asset_id}"


def load_asset(conn: db.Conn, asset_id: str, as_of_position: int | None = None) -> dict:
    events = chain.stream_events(conn, asset_stream(asset_id), as_of_position)
    state = catalog.rebuild(events)
    state["asset_id"] = asset_id
    return state


def submit(conn: db.Conn, *, asset_id: str | None, event_type: str, payload: dict,
           actor_role: str, actor_id: str | None = None, expected_version: int | None = None,
           command_id: str | None = None, occurred_at=None, stream_id: str | None = None,
           source: str = "WEB") -> dict:
    """One entry point for every command. Returns the appended event row."""
    if event_type not in catalog.EVENTS:
        raise Denied(f"unknown event type {event_type}")
    if event_type not in ROLE_RIGHTS.get(actor_role, set()):
        raise Denied(f"role {actor_role} may not record {event_type}")

    stream = stream_id or asset_stream(asset_id)
    if stream.startswith("asset:"):
        state = load_asset(conn, asset_id)
        ok, why = catalog.can_apply(state, event_type)
        if not ok:
            raise Denied(why)
        if expected_version is not None and expected_version != state["version"]:
            raise chain.Conflict(stream, state["version"])
        expected_version = state["version"]

    trust, _ = catalog.EVENTS[event_type]
    return chain.append(
        conn, stream_id=stream, event_type=event_type, payload=payload,
        actor_id=actor_id or f"user:{actor_role.lower()}", actor_role=actor_role,
        trust_level=trust, source=source, occurred_at=occurred_at,
        expected_version=expected_version if stream.startswith("asset:") else None,
        event_id=command_id or str(uuid.uuid4()))


# --------------------------------------------------------------------------- helpers used by the UI and seed
def register_asset(conn, *, asset_id, name, category, purok, acquired_on=None,
                   acquisition_cost=0, fund_source=None, backfilled=False,
                   actor_role="SECRETARY", occurred_at=None, command_id=None):
    return submit(conn, asset_id=asset_id, event_type="AssetRegistered", actor_role=actor_role,
                  occurred_at=occurred_at, command_id=command_id,
                  payload={"asset_id": asset_id, "name": name, "category": category,
                           "location": {"purok": purok}, "acquired_on": acquired_on,
                           "acquisition_cost": acquisition_cost, "fund_source": fund_source,
                           "backfilled": backfilled})


def record_inspection(conn, *, asset_id, condition, findings="", actor_role="FIELD_WORKER",
                      occurred_at=None, command_id=None, expected_version=None):
    return submit(conn, asset_id=asset_id, event_type="InspectionRecorded", actor_role=actor_role,
                  occurred_at=occurred_at, command_id=command_id, expected_version=expected_version,
                  payload={"condition": condition, "findings": findings})


def record_damage(conn, *, asset_id, severity, service_disrupted=False, hazard_id=None,
                  estimated_cost=0, actor_role="FIELD_WORKER", occurred_at=None, command_id=None):
    return submit(conn, asset_id=asset_id, event_type="DamageRecorded", actor_role=actor_role,
                  occurred_at=occurred_at, command_id=command_id,
                  payload={"severity": severity, "service_disrupted": bool(service_disrupted),
                           "hazard_id": hazard_id, "estimated_cost": estimated_cost})


def report_issue(conn, *, asset_id, issue_category, description="", command_id=None, occurred_at=None):
    return submit(conn, asset_id=asset_id, event_type="IssueReported", actor_role="PUBLIC",
                  actor_id="public:qr", source="QR_PUBLIC", command_id=command_id,
                  occurred_at=occurred_at,
                  payload={"issue_id": str(uuid.uuid4()), "issue_category": issue_category,
                           "description": description})


def triage_issue(conn, *, asset_id, issue_id, decision, reason="", actor_role="SECRETARY",
                 occurred_at=None, command_id=None):
    return submit(conn, asset_id=asset_id, event_type="IssueTriaged", actor_role=actor_role,
                  occurred_at=occurred_at, command_id=command_id,
                  payload={"issue_id": issue_id, "decision": decision, "reason": reason})


def open_work_order(conn, *, asset_id, priority="P3", due_on=None, source_issue_id=None,
                    actor_role="SECRETARY", occurred_at=None, command_id=None):
    return submit(conn, asset_id=asset_id, event_type="WorkOrderOpened", actor_role=actor_role,
                  occurred_at=occurred_at, command_id=command_id,
                  payload={"work_order_id": str(uuid.uuid4()), "priority": priority,
                           "due_on": due_on, "source_issue_id": source_issue_id})


def start_repair(conn, *, asset_id, work_order_id, actor_role="FIELD_WORKER",
                 occurred_at=None, command_id=None):
    return submit(conn, asset_id=asset_id, event_type="RepairStarted", actor_role=actor_role,
                  occurred_at=occurred_at, command_id=command_id,
                  payload={"work_order_id": work_order_id})


def complete_repair(conn, *, asset_id, work_order_id, actual_cost=0, resulting_condition="GOOD",
                    fund_source="BARANGAY_DEVELOPMENT_FUND", actor_role="FIELD_WORKER",
                    occurred_at=None, command_id=None):
    return submit(conn, asset_id=asset_id, event_type="RepairCompleted", actor_role=actor_role,
                  occurred_at=occurred_at, command_id=command_id,
                  payload={"work_order_id": work_order_id, "actual_cost": actual_cost,
                           "resulting_condition": resulting_condition, "fund_source": fund_source})


def declare_hazard(conn, *, hazard_id, name, hazard_type, started_on, ended_on=None,
                   actor_role="PUNONG_BARANGAY", occurred_at=None, command_id=None):
    return submit(conn, asset_id=None, stream_id=f"hazard:{hazard_id}", event_type="HazardDeclared",
                  actor_role=actor_role, occurred_at=occurred_at, command_id=command_id,
                  payload={"hazard_id": f"hazard:{hazard_id}", "name": name,
                           "hazard_type": hazard_type, "started_on": started_on, "ended_on": ended_on})


def seal_turnover(conn, *, psgc, outgoing_term, incoming_term, witnesses, actor_role="PUNONG_BARANGAY"):
    cp = chain.create_checkpoint(conn, reason="TURNOVER")
    assets = conn.one("SELECT COUNT(*) AS c FROM proj_asset_current")
    return submit(conn, asset_id=None, stream_id=f"barangay:{psgc}", event_type="TurnoverSealed",
                  actor_role=actor_role,
                  payload={"checkpoint_position": cp["position"], "checkpoint_hash": cp["head_hash"],
                           "outgoing_term": outgoing_term, "incoming_term": incoming_term,
                           "asset_count": (assets or {}).get("c", 0), "witnesses": witnesses})
