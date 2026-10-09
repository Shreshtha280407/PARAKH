# server/ — backend (P2 + P2.1)

FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL. Covers: pack import,
assessor/admin auth (argon2 + JWT), worker capability tokens, assessment +
evidence metadata, a real resumable evidence upload protocol (chunked,
server-verified SHA-256), a durable PostgreSQL-backed job queue + worker,
and a seeded assessor queue.

See `docs/gates/P2_1.md` for the full acceptance checklist and
`docs/worker_capability_tokens.md` / `docs/evidence_status_model.md` for
the two design docs this phase leans on most.

## Setup

```
python3 -m venv server/.venv
source server/.venv/bin/activate
pip install -r server/requirements.txt
```

## Running the whole stack (recommended)

`docker compose -f infra/docker-compose.yml up -d --build` runs Postgres +
API + worker + dashboard together — see `infra/README.md` for the full
clean-start / shutdown / reset commands. That's the easiest way to run
this for real.

## Running the API directly (no Docker)

Point `DATABASE_URL` at a reachable Postgres (or SQLite for quick local
iteration — same models, same migration, verified against both):

```
export DATABASE_URL="postgresql+psycopg://parakh:parakh_dev_pw@localhost:5432/parakh"
# or: export DATABASE_URL="sqlite:///$(pwd)/server/data/dev.db"
cd server && alembic upgrade head
export DEV_ASSESSOR_PASSWORD="pick-something"   # otherwise the seeded assessor can't log in
python -m server.app.seed
uvicorn server.app.main:app --reload --port 8000
```

All other settings (`JWT_SECRET`, `EVIDENCE_DIR`, etc.) have dev-friendly
defaults in `server/app/config.py` — see `.env.example` at the repo root
for the full list and what each one does.

**Don't reuse a database across both automated tests and manual/demo
use.** `server/tests/conftest.py`'s Postgres branch (`TEST_DATABASE_URL`)
drops and recreates every table on each test run — pointed at the same
database you're using for manual verification, a test run will wipe your
seeded data out from under you. Use separate databases (or just use the
Docker stack's `db`, which pytest never touches).

## Tests

```
python -m pytest server/tests
```

Separate from the P1 test suite (`tools/pack_validate.py`,
`tools/audit_qp_traceability.py`, `ml/mapping/test_*.py`, and
`tests/fixtures/` at the repo root — no Python, no pytest, no server
involved). Runs against an in-memory SQLite database per test by default
(fast, no Docker needed).

**One test requires real PostgreSQL and is not skippable without it**:
`test_jobs.py::test_concurrent_claims_never_double_process` proves
`SELECT ... FOR UPDATE SKIP LOCKED` actually prevents two workers from
claiming the same job — SQLite has no row-level locking, so this can't be
demonstrated against it, and the test fails loudly (not a silent skip) if
`TEST_DATABASE_URL` isn't set to a Postgres URL. Run the full suite against
real Postgres (what CI does):

```
docker compose -f infra/docker-compose.yml up -d db   # just the db service
export TEST_DATABASE_URL="postgresql+psycopg://parakh:parakh_dev_pw@localhost:5432/parakh"
python -m pytest server/tests
```

## OpenAPI contract

```
python tools/export_openapi.py          # regenerate contracts/openapi.json
python tools/export_openapi.py --check  # CI: fail if it's stale
```

## What's still explicitly out of scope (later phases, not this branch)

- Evidence bytes read-back (no "download this evidence" endpoint — write
  path only, by design, see `docs/safety.md`).
- Android sync.
- Scoring, reports, reassessment (P6/P7).
- CV/AI inference, thumbnailing (the worker's `verify_evidence` job
  re-checks a stored file's SHA-256, nothing more).
- Polished dashboard UX (`apps/dashboard` is intentionally basic/functional).
