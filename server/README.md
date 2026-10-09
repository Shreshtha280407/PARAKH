# server/ — P2 backend

FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL. Scope is deliberately narrow
(master plan P2): pack import, assessment/evidence **metadata** (no bytes),
a private local storage interface, upload **sessions** with quota checks
(no chunk upload), a health endpoint, and a seeded assessor queue.

## Setup

```
python3 -m venv server/.venv
source server/.venv/bin/activate
pip install -r server/requirements.txt
```

## Database

Real target: PostgreSQL via `infra/docker-compose.yml`:

```
docker compose -f infra/docker-compose.yml up -d
cd server && alembic upgrade head
```

Local dev without Docker: point `PARAKH_DATABASE_URL` at a SQLite file
instead (same models, same migration — Alembic was verified against both):

```
export PARAKH_DATABASE_URL="sqlite:///$(pwd)/server/data/dev.db"
cd server && alembic upgrade head
```

## Seed demo data + run

```
python -m server.app.seed              # imports packs/ae-con-q0602, adds a demo assessor + 3 workers + 3 assessments
uvicorn server.app.main:app --reload   # http://127.0.0.1:8000/health, /queue, /assessments, /uploads
```

## Tests

```
python -m pytest server/tests
```

Separate from the P1 test suite (`tools/pack_validate.py`,
`tools/audit_qp_traceability.py`, `ml/mapping/test_*.py`, and
`tests/fixtures/` at the repo root, which test `packs/ae-con-q0602/` pack
data directly — no Python, no pytest, no server involved). P2's tests run
against an in-memory SQLite database per test (fast, no Docker needed); the
schema itself was separately verified against a real on-disk SQLite
database via `alembic upgrade head` / `downgrade base`, and the whole app
was smoke-tested with a real `uvicorn` process answering real HTTP requests
over curl. None of that is a substitute for running the full suite against
real PostgreSQL via `infra/docker-compose.yml` before P2 is considered
done — this repo's environment has no Docker daemon available to do that
here.

## What's NOT here yet (explicitly out of P2 scope)

- Evidence upload **bytes** (`PUT /uploads/{id}/chunks/{n}`, `POST
  /uploads/{id}/complete`) — only session-open with quota checks exists.
- Android sync.
- Scoring, reports, reassessment (P6/P7).
- Background job runner (`server/worker.py`) — nothing async-heavy exists
  yet that needs one.
- Auth (JWT/argon2/PIN hashing) — `users` has no password/PIN column yet;
  `worker_id`/`pack_id` are passed directly in request bodies for now.
