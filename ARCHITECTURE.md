# Architecture

One sentence: **the log is the system; everything else is a view of it.**

```
 producers                command side              log                consumers            query side
 ---------                ------------              ---                ---------            ----------
 resident QR page  ─┐                                                 registry+timeline ─┐
 officer web app   ─┼─► commands.submit() ──► chain.append() ──► es_events ──► projector ─┼─► proj_* tables ──► api.py ──► web UI
 field worker      ─┤     validate role        hash + link       (append only)    idempotent,        (disposable)
 scheduler         ─┘     rebuild stream       one transaction                    gap-filling
                          check lifecycle            │
                                                     └──► chain.create_checkpoint() ──► witness copies (outside the barangay)
```

## Invariants (do not break these)

1. **The log is append-only.** Nothing updates or deletes `es_events`. Mistakes are fixed by
   appending `EntryCorrected`. Database triggers enforce it; the hash chain catches anyone
   who turns the triggers off.
2. **Hashes are computed exactly one way.**
   `event_hash = SHA-256(prev_hash ‖ stream_prev_hash ‖ int64_be(position) ‖ JCS(envelope))`,
   hex-encoded, where JCS is RFC 8785 canonical JSON. `backend/chain.py` is the reference; any
   other implementation (the Java Command API, for example) must match it byte for byte.
3. **The command side never reads a projection to decide anything.** It rebuilds the target
   stream with `commands.load_asset()` and checks `catalog.can_apply()`. Read models can be
   stale or missing without ever causing an invalid write.
4. **Projections are disposable.** Any projection can be deleted and replayed
   (`POST /api/admin/rebuild`). If a rebuild differs from the live projection, the projector
   has a bug, not the log.
5. **Trust level is part of the record.** A resident scan produces `IssueReported`
   (`PUBLIC_CLAIM`), never an inspection result. Only an officer's event is
   `OFFICER_ATTESTED`, and high-impact events are `APPROVED`.
6. **Personal data never enters an event.** The demo stores none at all; production puts it in
   an encrypted vault keyed by `subject_ref` so a key deletion erases it without touching the log.

## Modules

| File | Responsibility | Do not put here |
|---|---|---|
| `backend/chain.py` | hashing, append, read, checkpoints, verify | domain rules |
| `backend/catalog.py` | event types, lifecycle, summaries | database access |
| `backend/commands.py` | validation, role rights, command helpers | read-model queries |
| `backend/projector.py` | read models, offsets, gap filling, rebuild | decisions that affect writes |
| `backend/api.py` | HTTP surface | business rules |
| `backend/demo_tamper.py` | demo-only attacker | anything the real system depends on |

## Streams

| Stream id | Holds |
|---|---|
| `asset:BGY-{PSGC}-{CAT}-{serial}` | one asset's whole life |
| `hazard:{id}` | a declared typhoon, flood or fire |
| `barangay:{psgc}` | registry initialisation, turnover seals |
| `user:{id}` | enrolment and deactivation, so the log records who could write |

## Lifecycle

```
                damage / poor inspection / accepted report
   IN_SERVICE ─────────────────────────────────────────► NEEDS_ATTENTION
        ▲  ▲                good/fair inspection  ◄──────────┘   │ RepairStarted
        │  └───────────────────────────────────────────────┐     ▼
        │            RepairCompleted (good/fair)           └── UNDER_REPAIR
        │                                                        │
        └── declared unserviceable (approval) ──► UNSERVICEABLE ──┴──► DISPOSED
```

Observations (inspection, damage, resident report) are accepted in any state except
`DISPOSED`. Transitions (start repair, complete repair, declare unserviceable) are not.

## Delivery, and what changes when RabbitMQ arrives

Today `api.py` calls `projector.run_once()` after each write and before each read. That is
the same consumer logic the broker path uses, minus the broker. To switch:

1. Run the relay: tail `es_events` past a bookmark, publish `{stream type}.{event type}` to a
   topic exchange with publisher confirms, advance the bookmark after the confirm.
2. Run each consumer as its own process with a durable queue and a dead-letter queue.
3. Keep `projector.handle()` exactly as it is: it already takes one event, skips duplicates by
   offset, and fills gaps from the log.

Nothing else moves, because the broker was never the source of truth.

## Mapping to the paper

| Paper | Here |
|---|---|
| Section 5 architecture (Fig. 1) | this file |
| Section 6 domain model and vocabulary | `backend/catalog.py`, `docs/events/catalog.v1.json` |
| Section 7 hash chain, checkpoints, verification | `backend/chain.py`, Integrity tab |
| Section 8 relay and projectors | `backend/projector.py`, `TODO.md` for the broker |
| Section 11 experiments E1, E3 | `tests/test_chain.py`, `/api/demo/tamper` |
