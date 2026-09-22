# BAGAY demo

An event-sourced, tamper-evident registry for barangay public infrastructure.
This repository is the running demo that goes with the paper draft (`docs/`).

Everything you see in the UI is derived from one append-only, hash-chained event log.
Delete the read models and they rebuild identically. Tamper with the log and verification
says exactly what changed.

## Run it (about 60 seconds)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open http://localhost:8000. The first run seeds a fictional barangay with roughly 1,300
events spanning 2023 to 2026, including two hazards and a backlog of work orders.

```bash
python run.py --reset        # wipe and re-seed
python run.py --port 9000    # different port
pytest -q                    # the tests that back the claims below
```

No internet, no Docker, no Node. SQLite by default, PostgreSQL with one environment
variable (see below).

## The five-minute demo

Follow `DEMO_SCRIPT.md`. The short version:

1. **Dashboard** shows 110 assets and the head of the log.
2. **Assets** opens one asset's full history, with a resident report, an inspection, a
   repair and its cost, and who recorded each. "State as of a past point" replays the
   stream to any earlier position.
3. **Work queue** turns a resident claim into an officer-attested work order.
4. **Insights** counts damage and service disruptions per hazard, which is the shape SDG
   indicator 11.5.3 asks for.
5. **Integrity** verifies the chain, then lets you tamper with the database on purpose.
   Editing one row is caught by the chain alone. Rewriting every later hash, or deleting
   the newest events, is caught only by the checkpoints held by witnesses. That contrast is
   the point of the paper.

## Layout

```
run.py                 start everything
backend/
  db.py                SQLite / PostgreSQL wrapper
  schema.sql           demo schema (production DDL is in docs/production-db/)
  chain.py             hash chain: append, read, checkpoint, verify   <- the executable spec
  catalog.py           event vocabulary, lifecycle, bilingual summaries
  commands.py          command side: validate against the stream, then append
  projector.py         consumers: idempotent read models, rebuildable
  api.py               FastAPI: commands, queries, verification, demo controls
  seed.py              the fictional Barangay Halimbawa
  demo_tamper.py       DEMO ONLY: plays the insider who edits the log
web/                   no-build UI (plain JS; the production client is React + Vite)
tests/                 pytest: hashing, idempotency, conflicts, tamper detection, rebuild
docs/                  paper design pack: production schema, event catalog, OpenAPI
```

## Switching to PostgreSQL

```bash
docker compose up -d postgres            # or use any PostgreSQL 16
export BAGAY_DB=postgresql://bagay:bagay@localhost:5432/bagay
pip install "psycopg[binary]"
python run.py --reset
```

The demo schema is portable SQL. The production DDL with JSONB, BYTEA, enums and
`SECURITY DEFINER` triggers is in `docs/production-db/`.

## What is real and what is demo-grade

| Real, as specified in the paper | Demo-grade shortcut |
|---|---|
| Hash chain and verification, byte for byte | SQLite instead of PostgreSQL by default |
| Event vocabulary, trust levels, lifecycle rules | No authentication; roles are chosen in the UI |
| Command side validates against the stream, never a projection | Command and query APIs run in one process |
| Idempotent projectors with offsets and rebuild | Consumers are pumped in-process; RabbitMQ not wired yet |
| Checkpoints, witnesses, turnover pack export | Witness copies live in a local table |
| Optimistic concurrency and duplicate suppression | No offline PWA yet |

`TODO.md` tracks the gap. `NOTES.md` explains why each shortcut was taken.
