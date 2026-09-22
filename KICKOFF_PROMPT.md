# Kickoff prompt for the next session

Copy everything between the lines into a new session, and attach `bagay-demo.zip`
(or open the folder if you are working locally with the repo on disk).

---

I'm continuing work on BAGAY, my group's event-driven architecture project at Mapúa. I've
attached the repo (`bagay-demo.zip`). It already runs: `pip install -r requirements.txt`
then `python run.py` serves a working demo on port 8000 with about 1,300 seeded events.

Start by reading, in this order: `CLAUDE.md`, `ARCHITECTURE.md`, `TODO.md`, `NOTES.md`.
They carry the project rules, the invariants, and what is already done. `docs/` holds the
production PostgreSQL schema, the event catalog and the OpenAPI spec from the paper.

Ground rules that matter more than speed:
- The event log is append-only. Corrections are new events, never updates.
- The hash input format in `backend/chain.py` is fixed; if it ever changes, update
  `docs/reference_chain.py`, the tests and the paper in the same change.
- The command side never reads a projection to decide anything.
- Do not invent evaluation numbers. Measured results only.
- Keep `python run.py` working offline with no Docker and no Node at every step.

Before you change anything, verify the baseline:

```
pytest -q
python run.py --reset && python run.py &
curl -X POST localhost:8000/api/verify          # expect ok: true
curl -X POST localhost:8000/api/admin/rebuild   # expect identical: true
```

Then work through `TODO.md` from the top, in small commits, running `pytest -q` after each.
Ask me before doing anything that changes the hash format, the event vocabulary, or the
paper's claims. When you finish a work item, update `TODO.md` and `CLAUDE.md` so the next
session starts where you stopped.

Today I want: <SAY WHAT YOU WANT HERE, for example "the RabbitMQ relay and one real consumer
process" or "the Java Command API producing identical hashes" or "experiment E3 with 100
randomised trials per cell">.

---

## Tips

- If you are handing this to a teammate instead of an assistant, point them at `README.md`
  and `DEMO_SCRIPT.md` first; they do not need the rest to run it.
- If the demo has to be shown before any of that work lands, the current state is already
  demo-ready. `DEMO_SCRIPT.md` is a five-minute walkthrough.
- Keep the zip and the paper together. The claims in the paper and the behaviour of the code
  are meant to be checked against each other.
