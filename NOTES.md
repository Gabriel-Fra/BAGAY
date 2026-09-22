# Notes: decisions, deviations, and things that bit us

## Why SQLite in the demo

The design specifies PostgreSQL, and `docs/production-db/` is written for it. The demo
defaults to SQLite so the whole thing starts with two commands on any laptop, offline, five
minutes before a presentation. Nothing about the research claim depends on the engine: the
hash chain, the event model, the projectors and the verifier are identical, and
`BAGAY_DB=postgresql://...` switches over. Hashes are stored as hex TEXT in both so the two
paths produce the same bytes.

## Why the projectors run in-process

RabbitMQ is in the design and stays in the plan. For the demo it would add a service to
install and explain without changing what anyone sees. `projector.run_once()` is the same
consumer logic a broker-driven consumer would run: it tracks an offset, skips duplicates and
fills gaps from the log. Wiring the broker is a delivery change, not a rewrite, which is
itself a point worth making in the demo.

## Tamper results (measured on the seeded log, 1,333 events, 7 checkpoints)

| Attack | Chain only | Chain + witnessed checkpoints |
|---|---|---|
| Edit one payload | detected (CONTENT_ALTERED) | detected |
| Delete one event | detected (BROKEN_LINK, GAP_OR_REORDER) | detected |
| Delete the newest events | **missed** | detected (TRUNCATED) |
| Edit, then recompute every later hash | **missed** | detected (CHECKPOINT_MISMATCH) |

This is exactly the argument in Section 7 of the paper: a chain alone stops casual edits, and
only a copy held outside the operator's reach stops a determined insider. It is a design
sanity check on synthetic data, not experiment E3, which needs 100 randomised trials per cell
on the real implementation.

## Things that bit us while building

- **Deleting the SQLite file while a connection is open** silently keeps the old data alive on
  the unlinked inode. The demo reset now empties tables through the live connection instead.
- **`INSERT OR REPLACE` with a single-column primary key** collapsed the three witness channels
  into one row. The witness table is keyed by `(position, channel)`.
- **Projector offsets with type filters** look like permanent gaps if the offset only advances
  to the last matching event. When a consumer is caught up, its offset moves to the head of
  the log.
- **Canonical JSON matters.** Timestamps are truncated to milliseconds before hashing, because
  a value that is stored differently from the way it was hashed breaks verification later.

## Deliberately not done

- No authentication. Roles are picked in the UI. Do not demo this as production-ready.
- No photo uploads; the design stores SHA-256 digests in the event and the file in an object
  store.
- No personal data anywhere, so the vault and crypto-shredding path is designed but unused.
- Insights use transparent counts only. No scoring model, no forecasting.
