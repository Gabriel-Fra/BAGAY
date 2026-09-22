# TODO

Ordered by what unblocks the paper and the course deliverable.

## Next session (highest value first)

- [ ] **Java Command API parity.** Port `chain.compute_hash` and `commands.submit` to Spring
      Boot; prove it by hashing the same 1,000 events in both and comparing digests. Everything
      else in the Java plan depends on this.
- [ ] **PostgreSQL as the default for the team**, using `docs/production-db/001_event_store.sql`
      with its triggers and least-privilege roles.
- [ ] **RabbitMQ relay and one real consumer process.** Log-tailing relay with publisher
      confirms, durable queue, dead-letter queue. Keep `projector.handle()` unchanged.
- [ ] **Experiment E1** (replay correctness): property-based tests with Hypothesis comparing
      incremental projection, full rebuild, and a pure reference model.
- [ ] **Experiment E3** (tamper detection): 100 randomised trials per attack and configuration,
      attack positions sampled before and after the last checkpoint, report detection rate and
      verification time.

## Then

- [ ] Authentication and the two-person rule for approved events.
- [ ] Offline capture: PWA outbox, `/api/commands/batch`, observation versus transition rebasing.
- [ ] Photo uploads, content-addressed, EXIF stripped on the device.
- [ ] QR tag sheet generator (segno is already a dependency) and the `/a/{asset}` landing page
      as the real public entry point.
- [ ] Experiments E2, E4 to E7 (rebuild cost, consumer outage, burst, duplicates, offline sync).
- [ ] RQ1 interviews with barangay staff; then revise the event vocabulary and the requirements
      table in the paper.
- [ ] Port the UI to React + TypeScript + Vite once the endpoints stop moving.

## Paper

- [ ] Fill Section 12 (Results) with measured numbers only.
- [ ] Author names, e-mails, affiliation line; ethics clearance if the course requires it.
- [ ] Confirm the barangay count (42,010) against the PSA release itself.
