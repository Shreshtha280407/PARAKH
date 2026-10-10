# Worker capability tokens (P2.1, rotation/revocation added P2.2)

Product decision: the worker mobile app has no conventional login/signup.
Only assessors/admins get a web login (email + password, argon2 + JWT --
see `server/app/auth.py`). This document covers how worker-side API calls
are authorised instead, and its deliberate limitations.

## The mechanism

`POST /assessments` is open to any caller (no bearer token required — there
is no worker account to present one for). Its response includes a
`worker_token`: a random, URL-safe, 32-byte value (`secrets.token_urlsafe`,
see `server/app/worker_tokens.py`), returned **exactly once**, in that
response body only.

The server never stores the raw token. It stores `sha256(token)` on the
`assessments.worker_token_hash` column — the same pattern as an API key —
so a database leak doesn't hand out usable tokens.

Every worker-facing mutation after that point requires the token, sent as
an `X-Worker-Token` header, and it must match the specific assessment it's
scoped to:

- `POST /uploads` (open a resumable upload session)
- `PUT /uploads/{id}/chunks/{n}` (upload a chunk)
- `GET /uploads/{id}` (resume/status)
- `POST /uploads/{id}/complete` (finalise)
- `GET /assessments/{id}` (read own progress — this one also accepts an
  assessor/admin JWT, since assessors need to read the same endpoint for
  review)
- `POST /assessments/{id}/submit` (worker declares evidence capture done)
- `GET /assessments/{id}/report` (download own signed report, once one exists)

A raw numeric id alone (e.g. `assessment_id=42`) is never sufficient to act
on an assessment — a guess or an off-by-one on another device gets a 401,
not someone else's evidence.

## Rotation and revocation (P2.2)

An assessor/admin can now invalidate the current token and/or issue a
fresh one, via `server/app/routers/tokens.py`:

- `POST /assessments/{id}/worker-token/rotate` — overwrites
  `worker_token_hash` with a freshly generated token's hash and returns the
  new raw value once (same "returned exactly once" contract as creation).
  The old raw value stops working immediately, before the response is even
  sent back (the hash it matched no longer exists).
- `POST /assessments/{id}/worker-token/revoke` — sets
  `assessments.worker_token_status = "revoked"`. Every worker-token check
  across the API (`_require_worker_token_for_session`,
  `_assessor_or_worker_token`, `open_upload_session`, `submit_assessment`)
  verifies `worker_token_status == "active"` in addition to the hash match,
  so a revoked token is rejected even if its hash would otherwise still
  match. Rotating after a revoke reactivates the assessment with a fresh
  token (sets status back to `"active"`).

Both actions write an `AuditLog` row (`token_rotated` / `token_revoked`) --
see `docs/gates/P2_2.md` section 1.

## What this is not

This is a **bearer capability**, not an identity. Whoever holds the token
can act as that assessment's worker. It does not prove *which* worker, does
not prove liveness, and is not tied to a device fingerprint.

## Boundaries — still deliberately deferred, revisit before pilot

- **No expiry.** A token is valid for the assessment's entire lifetime
  unless an assessor explicitly rotates or revokes it -- there's still no
  automatic time-based invalidation.
- **No recovery.** If the token is lost (app uninstalled, phone lost) before
  the assessment reaches `submitted`, there is currently no flow to recover
  access to that assessment's draft evidence. A fresh `POST /assessments`
  starts a new one.
- **Transport security is assumed, not enforced here.** The token is a
  bearer value over HTTP headers; it relies on TLS in any real deployment
  (the Docker demo stack in `infra/docker-compose.yml` runs plain HTTP on
  localhost, which is fine for a demo, not for a pilot).
- **One token per assessment, not per worker.** A worker with multiple
  assessments holds multiple tokens, with no shared "worker session" concept.

None of this is meant to be the final answer for worker-side auth — it is
the smallest mechanism that replaces "trust a guessable integer" with
"require an unguessable secret," scoped exactly to what P2.1 needs
(resumable upload sessions) without inventing a worker login the product
explicitly does not want yet.
