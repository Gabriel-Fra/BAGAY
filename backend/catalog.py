"""Event vocabulary v1, the asset lifecycle, and human-readable summaries.

This file is the single place where "what an event means" lives. The command side uses
it to validate; the projector uses it to build read models. Keep it in sync with
events/catalog.v1.json in the design pack.
"""
from __future__ import annotations

import json

CATEGORIES = {
    "SL": "Streetlight", "DR": "Drainage or canal", "RD": "Road or pathway", "FB": "Footbridge",
    "BH": "Barangay hall", "CC": "Covered court", "HS": "Health station", "DC": "Day care centre",
    "EC": "Evacuation centre", "WS": "Water system", "CT": "CCTV", "GN": "Generator",
    "VH": "Vehicle", "RE": "Rescue equipment", "OT": "Other",
}

TRUST = {"PUBLIC_CLAIM": "Resident report", "OFFICER_ATTESTED": "Officer attested", "APPROVED": "Approved"}

IN_SERVICE, NEEDS_ATTENTION, UNDER_REPAIR = "IN_SERVICE", "NEEDS_ATTENTION", "UNDER_REPAIR"
UNSERVICEABLE, DISPOSED = "UNSERVICEABLE", "DISPOSED"

# event type -> (trust level it is recorded at, is it visible on the public QR page)
EVENTS = {
    "RegistryInitialized":        ("APPROVED", False),
    "AssetRegistered":            ("OFFICER_ATTESTED", True),
    "CustodyAssigned":            ("OFFICER_ATTESTED", False),
    "CustodyTransferred":         ("OFFICER_ATTESTED", False),
    "IssueReported":              ("PUBLIC_CLAIM", True),
    "IssueTriaged":               ("OFFICER_ATTESTED", True),
    "InspectionRecorded":         ("OFFICER_ATTESTED", True),
    "DamageRecorded":             ("OFFICER_ATTESTED", True),
    "WorkOrderOpened":            ("OFFICER_ATTESTED", True),
    "RepairStarted":              ("OFFICER_ATTESTED", True),
    "RepairCompleted":            ("OFFICER_ATTESTED", True),
    "AssetDeclaredUnserviceable": ("APPROVED", True),
    "AssetDisposed":              ("APPROVED", True),
    "EntryCorrected":             ("OFFICER_ATTESTED", True),
    "HazardDeclared":             ("OFFICER_ATTESTED", True),
    "TurnoverSealed":             ("APPROVED", True),
    "UserEnrolled":               ("APPROVED", False),
    "UserDeactivated":            ("APPROVED", False),
}

APPROVAL_REQUIRED = {"AssetDeclaredUnserviceable", "AssetDisposed", "TurnoverSealed"}


def payload_of(event: dict) -> dict:
    p = event.get("payload")
    return json.loads(p) if isinstance(p, str) else (p or {})


def initial_state() -> dict:
    return {
        "status": None, "condition": None, "name": None, "category": None, "purok": None,
        "custodian_role": None, "acquired_on": None, "acquisition_cost": 0.0, "fund_source": None,
        "last_inspected_at": None, "last_repaired_at": None, "open_issues": 0,
        "open_work_orders": 0, "lifetime_repair_cost": 0.0, "failure_episodes": 0,
        "version": 0, "head_hash": None, "position": 0,
    }


def apply(state: dict, event: dict) -> dict:
    """Fold one event into asset state. Pure: same events in, same state out."""
    p = payload_of(event)
    t = event["event_type"]
    was = state["status"]

    if t == "AssetRegistered":
        state.update(status=IN_SERVICE, condition="GOOD", name=p.get("name"),
                     category=p.get("category"), purok=(p.get("location") or {}).get("purok"),
                     acquired_on=p.get("acquired_on"),
                     acquisition_cost=float(p.get("acquisition_cost") or 0),
                     fund_source=p.get("fund_source"))
    elif t in ("CustodyAssigned", "CustodyTransferred"):
        state["custodian_role"] = p.get("to_role") or p.get("custodian_role") or state["custodian_role"]
    elif t == "IssueReported":
        state["open_issues"] += 1
    elif t == "IssueTriaged":
        state["open_issues"] = max(0, state["open_issues"] - 1)
        if p.get("decision") == "ACCEPTED" and state["status"] == IN_SERVICE:
            state["status"] = NEEDS_ATTENTION
    elif t == "InspectionRecorded":
        state["condition"] = p.get("condition")
        state["last_inspected_at"] = event["occurred_at"]
        if p.get("condition") in ("POOR", "UNSAFE"):
            if state["status"] == IN_SERVICE:
                state["status"] = NEEDS_ATTENTION
        elif state["status"] == NEEDS_ATTENTION and state["open_work_orders"] == 0:
            state["status"] = IN_SERVICE
    elif t == "DamageRecorded":
        state["condition"] = "UNSAFE" if p.get("severity") == "DESTROYED" else "POOR"
        if state["status"] in (IN_SERVICE, None):
            state["status"] = NEEDS_ATTENTION
    elif t == "WorkOrderOpened":
        state["open_work_orders"] += 1
        if state["status"] == IN_SERVICE:
            state["status"] = NEEDS_ATTENTION
    elif t == "RepairStarted":
        state["status"] = UNDER_REPAIR
    elif t == "RepairCompleted":
        state["open_work_orders"] = max(0, state["open_work_orders"] - 1)
        state["lifetime_repair_cost"] += float(p.get("actual_cost") or 0)
        state["last_repaired_at"] = event["occurred_at"]
        state["condition"] = p.get("resulting_condition", "GOOD")
        state["status"] = IN_SERVICE if p.get("resulting_condition", "GOOD") in ("GOOD", "FAIR") \
            else NEEDS_ATTENTION
    elif t == "AssetDeclaredUnserviceable":
        state["status"] = UNSERVICEABLE
    elif t == "AssetDisposed":
        state["status"] = DISPOSED

    # a failure episode starts whenever the asset leaves normal service
    if was == IN_SERVICE and state["status"] in (NEEDS_ATTENTION, UNDER_REPAIR):
        state["failure_episodes"] += 1

    state["version"] = event["stream_version"]
    state["head_hash"] = event["event_hash"]
    state["position"] = event["global_position"]
    return state


def rebuild(events: list[dict]) -> dict:
    state = initial_state()
    for e in events:
        apply(state, e)
    return state


def can_apply(state: dict, event_type: str) -> tuple[bool, str]:
    """Lifecycle guard. Observations are always allowed; transitions are not."""
    status = state["status"]
    if event_type == "AssetRegistered":
        return (status is None, "asset already registered")
    if status is None:
        return (False, "unknown asset")
    if status == DISPOSED:
        return (False, "asset is disposed; its history is closed")
    if event_type == "RepairStarted":
        return (status in (NEEDS_ATTENTION, UNDER_REPAIR), "no open need for repair")
    if event_type == "RepairCompleted":
        return (status == UNDER_REPAIR, "no repair in progress")
    if event_type == "AssetDisposed":
        return (status == UNSERVICEABLE, "declare the asset unserviceable first")
    if event_type == "AssetDeclaredUnserviceable":
        return (status != UNSERVICEABLE, "already unserviceable")
    return (True, "")


# --------------------------------------------------------------------------- summaries
def summarize(event: dict) -> tuple[str, str]:
    p = payload_of(event)
    t = event["event_type"]
    peso = lambda v: f"PHP {float(v or 0):,.0f}"                                    # noqa: E731
    table = {
        "AssetRegistered": (
            f"Registered: {p.get('name', 'asset')}" + (" (from paper records)" if p.get("backfilled") else ""),
            f"Nairehistro: {p.get('name', 'ari-arian')}"),
        "CustodyAssigned": (f"Custody assigned to {p.get('custodian_role', 'role')}",
                            f"Itinalaga ang pangangalaga sa {p.get('custodian_role', 'tungkulin')}"),
        "CustodyTransferred": (f"Custody transferred {p.get('from_role')} to {p.get('to_role')}"
                               f" ({p.get('reason', '')})",
                               f"Inilipat ang pangangalaga: {p.get('from_role')} to {p.get('to_role')}"),
        "IssueReported": (f"Resident report: {p.get('issue_category', 'issue').replace('_', ' ').lower()}",
                          f"Ulat ng residente: {p.get('issue_category', 'isyu').replace('_', ' ').lower()}"),
        "IssueTriaged": (f"Report {p.get('decision', '').lower()}", f"Ulat: {p.get('decision', '').lower()}"),
        "InspectionRecorded": (f"Inspection: condition {p.get('condition', '')}",
                               f"Inspeksyon: kalagayan {p.get('condition', '')}"),
        "DamageRecorded": (
            f"Damage recorded: {p.get('severity', '')}"
            + (f", {p.get('hazard_id', '').replace('hazard:', '')}" if p.get("hazard_id") else "")
            + (", service disrupted" if p.get("service_disrupted") else ""),
            f"Naitala ang pinsala: {p.get('severity', '')}"),
        "WorkOrderOpened": (f"Work order opened, priority {p.get('priority', '')}",
                            f"Binuksan ang work order, prayoridad {p.get('priority', '')}"),
        "RepairStarted": ("Repair started", "Sinimulan ang pagkumpuni"),
        "RepairCompleted": (f"Repair completed, {peso(p.get('actual_cost'))}"
                            f", now {p.get('resulting_condition', '')}",
                            f"Tapos na ang pagkumpuni, {peso(p.get('actual_cost'))}"),
        "AssetDeclaredUnserviceable": (f"Declared unserviceable: {p.get('reason', '')}",
                                       "Idineklarang hindi na magagamit"),
        "AssetDisposed": (f"Disposed ({p.get('mode', '')})", "Naitapon o nailipat"),
        "EntryCorrected": (f"Correction: {p.get('reason', '')}", f"Pagwawasto: {p.get('reason', '')}"),
        "HazardDeclared": (f"Hazard declared: {p.get('name', '')}", f"Idineklarang panganib: {p.get('name', '')}"),
        "TurnoverSealed": (f"Turnover sealed at position {p.get('checkpoint_position')}",
                           "Selyado ang turnover"),
        "RegistryInitialized": ("Registry initialised", "Sinimulan ang rehistro"),
    }
    return table.get(t, (t, t))
