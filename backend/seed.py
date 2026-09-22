"""Seed a fictional barangay with a decade of history, so the demo has something to show.

Barangay Halimbawa ("example") is invented. Every figure here is synthetic. The point is
that the history is long enough to cross a turnover and a typhoon, which is exactly the
situation the paper is about.
"""
from __future__ import annotations

import datetime as dt
import random

from . import chain, commands, db, projector

PSGC = "1380600000"                       # illustrative code, not a real barangay
BARANGAY = "Barangay Halimbawa"
PUROKS = ["Purok 1", "Purok 2", "Purok 3", "Purok 4", "Purok 5"]

PLAN = [                                  # (category, how many, name, unit cost)
    ("SL", 46, "Streetlight", 18_500), ("DR", 22, "Drainage line", 92_000),
    ("RD", 8, "Concrete pathway", 480_000), ("FB", 3, "Footbridge", 310_000),
    ("CC", 2, "Covered court", 1_850_000), ("HS", 1, "Health station", 2_400_000),
    ("DC", 2, "Day care centre", 1_250_000), ("EC", 1, "Evacuation centre", 3_100_000),
    ("WS", 4, "Water point", 145_000), ("CT", 9, "CCTV camera", 26_000),
    ("GN", 3, "Generator set", 210_000), ("VH", 2, "Patrol tricycle", 165_000),
    ("RE", 6, "Rescue equipment set", 48_000), ("BH", 1, "Barangay hall", 4_200_000),
]

HAZARDS = [
    ("2025-HABAGAT", "Habagat flooding (sample)", "FLOOD", dt.date(2025, 8, 3), dt.date(2025, 8, 9)),
    ("2026-TC-ESTER", "Typhoon Ester (sample)", "TYPHOON", dt.date(2026, 7, 19), dt.date(2026, 7, 24)),
]

ISSUE_KINDS = ["NOT_WORKING", "DAMAGED", "UNSAFE", "CLOGGED", "MISSING"]


def _d(date: dt.date, hour: int = 9) -> dt.datetime:
    return dt.datetime(date.year, date.month, date.day, hour, tzinfo=dt.timezone.utc)


def build(conn: db.Conn, *, assets_per_category=1.0, seed: int = 20260915) -> dict:
    rng = random.Random(seed)
    chain.append(conn, stream_id=f"barangay:{PSGC}", event_type="RegistryInitialized",
                 payload={"psgc": PSGC, "barangay_name": BARANGAY, "municipality": "Sample City",
                          "province": "Metro Manila", "term_label": "2023-2026"},
                 actor_role="SYSTEM", occurred_at=_d(dt.date(2023, 12, 1)))

    assets: list[dict] = []
    serial = 0
    for cat, count, label, unit in PLAN:
        for _ in range(max(1, int(count * assets_per_category))):
            serial += 1
            purok = rng.choice(PUROKS)
            acquired = dt.date(rng.randint(2014, 2024), rng.randint(1, 12), rng.randint(1, 28))
            asset_id = f"BGY-{PSGC}-{cat}-{serial:05d}"
            commands.register_asset(
                conn, asset_id=asset_id, name=f"{label}, {purok}", category=cat, purok=purok,
                acquired_on=acquired.isoformat(),
                acquisition_cost=round(unit * rng.uniform(0.85, 1.2), 2),
                fund_source=rng.choice(["BARANGAY_DEVELOPMENT_FUND", "GENERAL_FUND", "LGU_AID"]),
                backfilled=True, occurred_at=_d(dt.date(2023, 12, 2)))
            commands.submit(conn, asset_id=asset_id, event_type="CustodyAssigned",
                            actor_role="SECRETARY", occurred_at=_d(dt.date(2023, 12, 2)),
                            payload={"custodian_role": "SECRETARY", "document_ref": f"PAR-{serial:04d}"})
            assets.append({"id": asset_id, "cat": cat, "purok": purok, "unit": unit,
                           "state": "IN_SERVICE", "wo": None})

    for hid, name, kind, start, end in HAZARDS:
        commands.declare_hazard(conn, hazard_id=hid, name=name, hazard_type=kind,
                                started_on=start.isoformat(), ended_on=end.isoformat(),
                                occurred_at=_d(start))

    # ---------------------------------------------------------------- month by month
    day = dt.date(2024, 1, 15)
    stop = dt.date(2026, 9, 10)
    events_since_checkpoint = 0
    while day < stop:
        hazard = next((h for h in HAZARDS if h[3] <= day <= h[4] + dt.timedelta(days=20)), None)
        sample = rng.sample(assets, k=18 if not hazard else 30)
        for a in sample:
            roll = rng.random()
            when = _d(day, rng.randint(7, 16))
            if a["state"] == "UNDER_REPAIR":
                if roll < 0.7:
                    cost = round(a["unit"] * rng.uniform(0.03, 0.22), 2)
                    commands.complete_repair(conn, asset_id=a["id"], work_order_id=a["wo"],
                                             actual_cost=cost,
                                             resulting_condition=rng.choice(["GOOD", "GOOD", "FAIR"]),
                                             occurred_at=when)
                    a["state"], a["wo"] = "IN_SERVICE", None
                continue
            if a["state"] == "NEEDS_ATTENTION" and a["wo"]:
                if roll < 0.6:
                    commands.start_repair(conn, asset_id=a["id"], work_order_id=a["wo"], occurred_at=when)
                    a["state"] = "UNDER_REPAIR"
                continue
            if hazard and roll < 0.28:
                severity = rng.choices(["MINOR", "MAJOR", "DESTROYED"], [6, 3, 1])[0]
                commands.record_damage(conn, asset_id=a["id"], severity=severity,
                                       service_disrupted=severity != "MINOR",
                                       hazard_id=f"hazard:{hazard[0]}",
                                       estimated_cost=round(a["unit"] * rng.uniform(0.05, 0.6), 2),
                                       occurred_at=when, actor_role="KAGAWAD")
                a["state"] = "NEEDS_ATTENTION"
                wo = commands.open_work_order(conn, asset_id=a["id"],
                                              priority="P1" if severity != "MINOR" else "P3",
                                              due_on=(day + dt.timedelta(days=7)).isoformat(),
                                              occurred_at=when)
                a["wo"] = __import__("json").loads(wo["payload"])["work_order_id"]
            elif roll < 0.55:
                condition = rng.choices(["GOOD", "FAIR", "POOR", "UNSAFE"], [5, 4, 2, 1])[0]
                commands.record_inspection(conn, asset_id=a["id"], condition=condition,
                                           findings="Routine inspection", occurred_at=when)
                if condition in ("POOR", "UNSAFE") and a["state"] == "IN_SERVICE":
                    a["state"] = "NEEDS_ATTENTION"
                    wo = commands.open_work_order(conn, asset_id=a["id"],
                                                  priority="P1" if condition == "UNSAFE" else "P2",
                                                  due_on=(day + dt.timedelta(days=14)).isoformat(),
                                                  occurred_at=when)
                    a["wo"] = __import__("json").loads(wo["payload"])["work_order_id"]
            elif roll < 0.68:
                ev = commands.report_issue(conn, asset_id=a["id"],
                                           issue_category=rng.choice(ISSUE_KINDS),
                                           description="Reported by a resident through the QR page",
                                           occurred_at=when)
                if rng.random() < 0.75:                      # most reports get triaged quickly
                    issue_id = __import__("json").loads(ev["payload"])["issue_id"]
                    decision = rng.choices(["ACCEPTED", "DUPLICATE", "REJECTED"], [6, 2, 2])[0]
                    commands.triage_issue(conn, asset_id=a["id"], issue_id=issue_id,
                                          decision=decision,
                                          occurred_at=_d(day + dt.timedelta(days=1), 10))
                    if decision == "ACCEPTED" and a["state"] == "IN_SERVICE":
                        a["state"] = "NEEDS_ATTENTION"
                        wo = commands.open_work_order(conn, asset_id=a["id"], priority="P3",
                                                      due_on=(day + dt.timedelta(days=21)).isoformat(),
                                                      occurred_at=_d(day + dt.timedelta(days=1), 11))
                        a["wo"] = __import__("json").loads(wo["payload"])["work_order_id"]
            events_since_checkpoint += 1

        if events_since_checkpoint >= 120:                  # stands in for the daily checkpoint job
            chain.create_checkpoint(conn, reason="SCHEDULED")
            events_since_checkpoint = 0
        day += dt.timedelta(days=rng.randint(9, 20))

    chain.create_checkpoint(conn, reason="SCHEDULED")
    projector.rebuild_all(conn)
    head = chain.head(conn)
    return {"events": head["position"], "head_hash": head["head_hash"], "assets": len(assets)}


if __name__ == "__main__":
    db.init_db(reset=True)
    c = db.connect()
    print(build(c))
