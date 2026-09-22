# Project context for Claude (and any coding agent)

Read this first, then `ARCHITECTURE.md`. Keep this file updated as the project changes: it is
the memory that survives between sessions.

## What this is

BAGAY: an event-sourced, tamper-evident registry for barangay public infrastructure. It is a
university research project (Mapúa, event-driven architecture course) with a paper draft in
`docs/`. The demo in this repo is the working slice of that design.

The research claim is narrow and worth protecting: **an incoming barangay administration can
verify the history it inherits without trusting the outgoing one.** Anything that weakens
that claim (mutable history, hashes computed two different ways, checkpoints that only live
inside the same database) is a bug, not a shortcut.

## Ground rules

1. Never write code that updates or deletes rows in `es_events`. Corrections are new events.
2. Never change the hash input format in `backend/chain.py` without updating
   `docs/reference_chain.py`, the paper's Section 7, and the tests in the same commit. Other
   implementations depend on it byte for byte.
3. The command side must not read `proj_*` tables to make a decision.
4. Keep `backend/demo_tamper.py` and `/api/demo/*` clearly marked as demo-only. They must
   never be reachable in anything deployed to a real barangay.
5. Do not invent evaluation numbers. The paper's Results section is deliberately empty until
   experiments are actually run.
6. No personal data in events, ever. Roles and opaque references only.
7. Prefer boring, dependency-light code. The stack must start with
   `pip install -r requirements.txt && python run.py` on a laptop with no internet.

## Working state (update me)

- Demo: **works**. SQLite, seeded with roughly 1,300 events, all views functional.
- Tamper demo: all four attacks behave as the paper predicts (see `NOTES.md`).
- Java Command API: **implemented, not compiler-verified.** `java-command-api/` ports
  `chain.compute_hash` (via a hand-written RFC 8785 canonicalizer, no deps) and
  `commands.submit`'s validation. Built in a sandbox with no `javac` and no network, so it has
  never actually been compiled — run `java-command-api/build.sh` before trusting or checking
  off the TODO item. No Spring Boot/Maven wiring yet.
- Not built yet: RabbitMQ relay, PostgreSQL as the default, authentication, offline PWA,
  photo uploads, experiments E2 and E4 to E7.
- The paper is at draft v0.1 with results pending. Interviews (RQ1) not done.

## Conventions

- Python 3.11+, standard library first, type hints where they help.
- SQL uses `?` placeholders; `backend/db.py` translates for PostgreSQL.
- Event type names are PascalCase and past tense (`RepairCompleted`), never imperative.
- Timestamps are ISO 8601 UTC with milliseconds and a `Z` suffix; `occurred_at` is field time,
  `recorded_at` is server time. Both are hashed.
- Money is plain numbers in pesos; the UI formats them.
- The UI is plain JavaScript on purpose (no build step, works offline). The production client
  in the paper is React + TypeScript + Vite; port it when the team is ready, not before.

## How to check you have not broken anything

```bash
pytest -q                                   # hashing, idempotency, conflicts, tamper, rebuild
python run.py --reset && python run.py      # seeds cleanly and serves
curl -X POST localhost:8000/api/verify      # must report ok: true on a fresh seed
curl -X POST localhost:8000/api/admin/rebuild   # must report identical: true
```

If `/api/verify` reports findings on a log nobody tampered with, stop and fix that first.
It means append and verify disagree, which invalidates everything the demo claims.

## Where the design lives

- `docs/production-db/` PostgreSQL DDL with triggers and least-privilege roles
- `docs/events/catalog.v1.json` JSON Schema for every event payload
- `docs/api/openapi.yaml` the full API surface, including endpoints not built yet
- `docs/reference_chain.py` the same hash chain, written against PostgreSQL
- `NOTES.md` decisions and deviations; `TODO.md` what is next
