# server/ — backend (P2 / P2.1 / P2.2 / P6 / P7)

FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL. Covers: pack import,
assessor/admin auth (argon2 + JWT + cookie/CSRF), worker capability tokens
(rotate/revoke), assessment lifecycle + append-only audit log, a real
resumable evidence upload protocol (chunked, server-verified SHA-256) that
also carries and cryptographically verifies a P5 Android-sealed manifest
(ECDSA signature, TOFU device-key pinning, revision/idempotency binding —
see `server/app/manifest_verify.py`), a durable PostgreSQL-backed job queue
+ worker (evidence hash re-verification, video thumbnail extraction, real
ffprobe-based width/height/duration metadata), human PC scoring with
optimistic locking, a pinned-pack-data computed competency outcome
(`server/app/outcome.py` — NOS-wise thresholds + critical-PC rule, never an
invented constant), task-specific reassessment with versioned/resumable
recapture (unchanged tasks inherited by reference, never re-uploaded —
`server/app/routers/reassessment.py`), a worker-updates polling endpoint,
password-confirmed sign-off, PDF-first detached Ed25519 signing (immutable
stored PDF bytes, key-history-aware verification), a public
`GET /verify/{report_id}` endpoint, protected evidence content/thumbnail
serving, and a seeded assessor queue.

See `docs/gates/P2_1.md`, `docs/gates/P2_2.md`, `docs/gates/P6.md`,
`docs/gates/P7.md` for the full acceptance checklists and
`docs/worker_capability_tokens.md` / `docs/evidence_status_model.md` for
the two design docs P2.1 leans on most.

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

**`REPORT_SIGNING_PRIVATE_KEY` is required in every environment,
including development** — there is deliberately no auto-generate-on-
restart fallback, because that would silently invalidate every
previously-signed report the moment the process restarts. Generate one
once and keep it:

```
python -c "import secrets; print(secrets.token_bytes(32).hex())"
# put the printed hex string in .env as REPORT_SIGNING_PRIVATE_KEY=...
```

If you ever rotate it, move the old hex *public* key into
`REPORT_SIGNING_KEY_HISTORY` (comma-separated `key_id:hex_pubkey` pairs)
first — reports signed by a retired key must stay verifiable.
`tools/print_report_public_key.py` prints the current key's public half
(hex or `--pem`) for sharing with verifiers.

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

## Offline report verification

Every signed report is served as immutable PDF bytes plus a detached
JSON receipt (`{report_id, assessment_id, revision_number, pdf_sha256,
signature, key_id, signed_at}` — `GET /assessments/{id}/report?format=receipt`,
no password needed). `tools/verify_report.py` independently re-hashes a
downloaded PDF and checks the Ed25519 signature against a trusted public
key, entirely offline (no network call, no server trust):

```
python tools/verify_report.py report.pdf --pubkey <hex-or-.pem> [--receipt report.pdf.receipt.json]
```

A single modified byte in the PDF changes its SHA-256 and the tool exits
non-zero with `TAMPERED`; an unknown/wrong `key_id` exits non-zero with
`INVALID SIGNATURE`; a missing receipt fails closed rather than passing.
The browser-facing equivalent is the public, unauthenticated
`GET /verify/{report_id}` endpoint (and the dashboard's `#/verify/:id`
page the signed PDF's own QR code points at) — it only confirms the
*signature on record*, not that a particular PDF file you're holding
matches it; use `verify_report.py` for that.

## OpenAPI contract

```
python tools/export_openapi.py          # regenerate contracts/openapi.json
python tools/export_openapi.py --check  # CI: fail if it's stale
```

## What's still explicitly out of scope

- CV/AI quality inference (`EvidenceItem.quality_check_status` is a
  documented, unused contract for a future phase — see
  `docs/evidence_quality_result.md`).
- Polished dashboard UX (`apps/dashboard` is intentionally basic/functional).
- Any worker password login or an assessor mobile-app role (see
  `docs/worker_capability_tokens.md` — by design, not a gap).
