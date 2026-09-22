# Design pack (from the paper)

| Path | What it is |
|---|---|
| `production-db/001_event_store.sql` | PostgreSQL event store: hash chain, linkage and immutability triggers, checkpoints, least-privilege roles |
| `production-db/002_read_models.sql` | Projections, personal-data vault, users |
| `events/catalog.v1.json` | JSON Schema for all 18 event payloads |
| `api/openapi.yaml` | Full API surface, including endpoints the demo has not built yet |
| `reference_chain.py` | The same hash chain written against PostgreSQL (the executable spec) |
| `docker-compose.production.yml` | Reference deployment: Postgres, RabbitMQ, MinIO, the services |

The paper itself (PDF, Word and LaTeX source) is not in this repository. Keep it beside it, or
add it under `docs/paper/`.

The demo's own schema (`backend/schema.sql`) is a portable subset of the production DDL so the
demo can run on SQLite. Same columns, same hash inputs, fewer PostgreSQL-specific features.
