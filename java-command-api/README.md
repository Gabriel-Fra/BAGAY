# Java Command API (parity port)

Ports the byte-critical half of the command side to Java, per `TODO.md`'s "Java
Command API parity" item:

> Port `chain.compute_hash` and `commands.submit` to Spring Boot; prove it by
> hashing the same 1,000 events in both and comparing digests.

## What's here

```
src/main/java/bagay/
  chain/Json.java        JSON value model + hand-written parser (no deps)
  chain/Jcs.java          RFC 8785 (JCS) canonical serializer
  chain/Chain.java        event_hash = SHA-256(prev || stream_prev || int64_be(pos) || JCS(envelope))
  catalog/Catalog.java    trust levels + can_apply lifecycle guard, mirrors backend/catalog.py
  commands/Commands.java  role rights + submit() validation, mirrors backend/commands.py
src/test/java/bagay/chain/ParityCheck.java   standalone digest-comparison harness
build.sh                  javac-only compile + run (no Maven)
```

`tools/export_hash_vectors.py` (repo root) seeds a real log with `backend/seed.py`
and dumps every event's hashing inputs + expected `event_hash` as JSON. That
file is `ParityCheck`'s input.

## Why plain `javac` instead of Spring Boot / Maven

This was written in a sandbox with a JDK but no Maven and no network, so it
could not resolve any Maven dependency, including Spring Boot itself. Rather
than hand you an unbuildable `pom.xml`, this is dependency-free Java that
compiles with nothing but the JDK, and is structured so it drops into a Spring
Boot module later as plain `@Service`/`@Component` classes with no changes to
the hashing logic itself. Wiring it into Spring Boot (a `@RestController`,
JPA/JDBC repositories for `es_events`/`es_chain_head`/`es_stream_heads`, the
`SELECT ... FOR UPDATE` row lock) is real, not-yet-done work -- see "Not done"
below.

## Status: implemented, not yet compiler-verified

I could not run `javac` in the sandbox that produced this (no JDK compiler
installed, no network to get one), so **I have not personally compiled or run
this code, and TODO.md's item should stay unchecked until someone does.** Two
independent things are true, and it's worth keeping them separate:

1. **The algorithm is right** -- RFC 8785's number-formatting rule (every JSON
   number canonicalises as an ECMAScript `Number::toString`) was implemented
   by hand for Python too (`tools/export_hash_vectors.py` needed it, since this
   sandbox couldn't `pip install rfc8785` either), and re-verifying the real
   1,333-event seeded log against that hand-written implementation reported
   `ok: true` -- the same log Python's own `chain.verify` accepts. `Jcs.java`
   applies the identical algorithm, just starting from Java's `Double.toString`
   digit string instead of Python's `repr()`.
2. **The Java syntax has not been compiler-checked.** I read through it
   carefully (Java 21 pattern-matching `switch` over the sealed `JsonValue`
   hierarchy, record accessors, etc.) but a human read-through is not a
   substitute for `javac`.

### Run this yourself to actually close the TODO item

```bash
# 1. from the repo root, with the real project dependencies installed:
pip install -r requirements.txt
python -m tools.export_hash_vectors hash_vectors.json

# 2. compile and run the Java side against those vectors:
cd java-command-api
./build.sh ../hash_vectors.json
```

Expect either `PARITY OK: ...` or a mismatch list with position numbers and
expected-vs-actual digests. If you hit a `javac` error, that's the thing this
sandbox couldn't tell you about -- send it back and I'll fix it directly.

A `hash_vectors.json` generated this way (with the sandbox's hand-written JCS
substitute, not the real `rfc8785` package) is included at the repo root as a
starting point, but re-generate it with the real dependency before trusting
the result for the paper -- CLAUDE.md rule #5 (no invented numbers) applies to
this too.

## Not done (left for later TODO items)

- No Spring Boot wiring (`@RestController`, JPA/JDBC, `application.yml`).
- No database access at all: `Commands.submit` takes the chain head and
  stream head as plain arguments; the caller is responsible for reading them
  from `es_chain_head`/`es_stream_heads` (never `proj_*`, per ARCHITECTURE.md
  invariant #3) inside one transaction with the equivalent of `FOR UPDATE`,
  and for the actual `INSERT INTO es_events`.
- No idempotency-by-`event_id` check (Python's `chain.append` does this before
  touching the head; the Java port assumes the caller already resolved that).
- `Catalog`'s `apply`/`rebuild`/`summarize` (read-side folding and bilingual
  strings) are deliberately not ported -- ARCHITECTURE.md keeps that out of
  the command side.
