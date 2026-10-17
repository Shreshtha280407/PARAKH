# Hosted deployment: Vercel + Railway + Neon

> Historical deployment record. The reviewed open-access implementation and
> CI-coordinated release procedure are in [OPEN_ACCESS_RELEASE.md](OPEN_ACCESS_RELEASE.md).
> Git auto-deployment remains **NOT VERIFIED** until the owner pushes the
> implementation to `main` and the new workflows complete. Do not treat the
> historical branch counts, region or manual release instructions below as a
> current provider audit. Unsigned APKs now replace the old debug-signing fallback.

The three-provider hosted deployment of the P10 system. Complements
`docs/deployment/README.md` (local dev, offline/LAN, and the generic hosted
path) with the specific, actually-provisioned cloud deployment.

Nothing in this document is aspirational: every URL, revision and figure
below was read back from the live provider or the live service. Test results
are in `HOSTED_E2E_REPORT.md`; security verification in
`HOSTED_SECURITY_CHECKS.md`.

**Source commit:** branch `deploy/vercel-railway-neon`, based on `e53ecb3`
(P10 merge).

## 1. What is deployed where

| Component | Provider | Identity | Region |
|---|---|---|---|
| Assessor dashboard | Vercel Hobby | project `parakh-dashboard` | Vercel edge |
| FastAPI API | Railway (Trial) | project `parakh`, service `api` | `asia-southeast1` (Singapore) |
| Background worker | Railway (Trial) | project `parakh`, service `worker` | `asia-southeast1` (Singapore) |
| PostgreSQL | Neon Free | project `parakh` (`sparkling-band-45084780`) | `aws-ap-southeast-1` (Singapore) |
| Evidence object storage | Neon Object Storage (beta) | buckets `parakh-evidence`, `parakh-evidence-staging` | `ap-southeast-1` |

Singapore throughout: it is the closest region both providers share, which
keeps latency reasonable for Indian testers *and* keeps the Railway↔Neon hop
intra-region (the API and worker talk to Postgres and the bucket constantly;
a cross-region split there would dominate every request).

### Live URLs

| Purpose | URL |
|---|---|
| Assessor dashboard | https://parakh-dashboard-five.vercel.app |
| Public report verification | `https://parakh-dashboard-five.vercel.app/#/verify/{report_id}` |
| API health | https://api-production-c626.up.railway.app/health |
| API (Android clients) | `https://api-production-c626.up.railway.app` |

The dashboard reaches the API through its own origin at `/api/*` (see §4);
the Android app talks to the Railway host directly.

## 2. Neon

### Branches

Two branches, deliberately:

| Branch | Id | Role |
|---|---|---|
| `main` | `br-divine-leaf-b31f8cke` | Production. Migrated and pack-imported, **zero** transactional rows. Reserved for the team's real assessments. |
| `staging` | `br-green-king-b3x0m645` | Isolated test database. Everything the hosted test runs created lives here. |

**The currently deployed Railway services point at `staging`.** That is a
deliberate choice: it meant the entire hosted test suite could run against
real cloud infrastructure without putting a single synthetic row in the
database that will hold genuine worker assessments. Switching to production
is §7.

Each branch has its **own** bucket and its own S3 endpoint
(`https://{branch_id}.storage.c-4.ap-southeast-1.aws.neon.tech`), so test
evidence cannot land in the production bucket even by misconfiguration.

### Migrations

Applied with the existing Alembic migrations — no schema was generated from
ORM models:

```
ef0c3dd21d2a -> a3f9b4e90208 -> c1f9c6d7d164 -> 8bba80863fec
             -> 31f43e2b42be -> af3b2cddce3e -> b89e72c4d010 (head)
```

Both branches report `b89e72c4d010`, 19 tables.

**Use the DIRECT (unpooled) connection for migrations and the POOLED one for
runtime.** Neon's `env pull` provides both as `DATABASE_URL_UNPOOLED` and
`DATABASE_URL`. Alembic takes advisory locks and runs DDL, which a
transaction-mode pooler cannot be relied upon to hold across statements;
the API and worker, conversely, want the pooler so two processes' SQLAlchemy
pools do not exhaust the branch's connection allowance.

Migrations are run as an explicit one-off step from an operator machine, not
by the API or worker at startup — so two containers can never race the same
migration.

### Qualification pack

Imported with the repository's own importer (`python -m app.pack_import`),
verified on both branches:

| Field | Value |
|---|---|
| `qp_code` / `qp_version` | **CON/Q0602 / 4.0** |
| `pack_version` | `ae-con-q0602@v4.0-r1` |
| `source_pdf_sha256` | `27ef7dc3…e514ad` (matches the CI-pinned hash) |
| `final_evidence_budget_bytes` | `125829120` (120 MiB, unchanged) |
| NOS / PCs / rubric items / tasks | 8 / 119 / 71 / 5 |
| Critical rubric items | 26 (all 17 of T1 "Safety & PPE") |

Task budgets sum to exactly 125,829,120 bytes, matching the pack budget.
Import is idempotent — re-running it does not duplicate rows.

### Scale-to-zero

Neon suspends an idle compute and closes its connections. `server/app/db.py`
therefore configures `pool_pre_ping=True` (one cheap round-trip proves a
pooled connection is still alive, and transparently replaces it instead of
surfacing a random `OperationalError`), `pool_recycle=300`, and a bounded
pool (`pool_size=5`, `max_overflow=5`).

A suspended compute takes a few seconds to wake; the first request after a
long idle period is slow but succeeds.

## 3. Railway

Two services from one image, built from the repo root with
`server/Dockerfile` (it needs `tools/` and `packs/`, which live outside
`server/`):

| | `api` | `worker` |
|---|---|---|
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | `python -m app.worker` |
| Public domain | `api-production-c626.up.railway.app` | none |
| Healthcheck | `/health` | n/a |
| Restart policy | `ON_FAILURE` | `ALWAYS` |
| Replicas / sleep | 1 / disabled | 1 / disabled |

Railway's own PostgreSQL is deliberately **not** used — Neon is the database.

### Two pitfalls worth recording

1. **`$PORT` is not expanded.** Railway runs the start command without a
   shell, so `--port $PORT` reaches uvicorn as the literal string `$PORT`
   and it exits. The fix is an explicit `--port 8000` plus a `PORT=8000`
   service variable, so Railway's healthcheck and edge proxy both target
   8000. Without the `PORT` variable the app starts fine but the healthcheck
   probes a different port and the deploy is marked failed.
2. **Build context size.** `.dockerignore` now also excludes `apps/android`,
   `ml`, `docs` and `.github` — none are copied by `server/Dockerfile`. This
   takes a `railway up` upload from ~390 MB to ~5 MB.

### Environment variables

Set on both services (identical, so the worker sees the same database and
bucket). Values are never committed; secrets are pushed with
`railway variable set --stdin KEY` so they never appear in a shell history
or process list.

```
APP_ENV=staging
PORT=8000
RAILWAY_DOCKERFILE_PATH=server/Dockerfile

DATABASE_URL                      # Neon POOLED connection
JWT_SECRET  JWT_ALGORITHM=HS256  JWT_ISSUER  JWT_AUDIENCE  JWT_EXPIRE_MINUTES=60

REPORT_SIGNING_PRIVATE_KEY        # STABLE -- see warning below
REPORT_SIGNING_KEY_ID=parakh-hosted-1
REPORT_VERIFY_BASE_URL=https://parakh-dashboard-five.vercel.app
CORS_ALLOW_ORIGINS=https://parakh-dashboard-five.vercel.app
# COOKIE_DOMAIN deliberately UNSET -- the dashboard and API share one
# browser origin via the Vercel rewrite, so cookies are correctly host-only.

STORAGE_BACKEND=s3
S3_ENDPOINT_URL  S3_REGION=ap-southeast-1  S3_BUCKET
S3_ACCESS_KEY_ID  S3_SECRET_ACCESS_KEY

UPLOAD_SESSION_TTL_MINUTES=120  UPLOAD_CHUNK_MAX_BYTES=2097152
JOB_POLL_INTERVAL_SECONDS=2.0  JOB_MAX_ATTEMPTS=3  JOB_LEASE_SECONDS=300
```

> **Never rotate `REPORT_SIGNING_PRIVATE_KEY`.** P7 stores a detached
> Ed25519 signature per report; replacing this key makes every
> already-signed report fail verification. If it must ever be rotated, move
> the old public key into `REPORT_SIGNING_KEY_HISTORY` first so existing
> reports stay verifiable.

`CORS_ALLOW_ORIGINS` must be a real non-localhost HTTPS origin: `config.py`
fail-fasts on a localhost origin whenever `APP_ENV != development`, so the
container will refuse to start if this is left at its default.

## 4. Vercel, and the cross-site cookie problem

PARAKH authenticates assessors with an **HttpOnly, `SameSite=Lax`** session
cookie plus a readable CSRF cookie (double-submit). `parakh-dashboard-*.vercel.app`
and `api-production-*.up.railway.app` are different sites, so a cross-site
XHR would never send that cookie — and adding a CORS origin does not change
that. `SameSite=None` would work but weakens the cookie, and moving the
token to `localStorage` would discard the HttpOnly protection entirely.

**The deployment instead makes the API same-origin** via a Vercel rewrite
(`apps/dashboard/vercel.json`):

```
/api/:path*  ->  https://api-production-c626.up.railway.app/:path*
```

The dashboard is built with `VITE_API_BASE_URL=/api`, so every call it makes
— including `<img>`/`<video>` sources, the signed-PDF download and the
public verify endpoint — is a relative, same-origin request. The browser
sends the `SameSite=Lax` cookie normally, CSRF stays fully enforced, and no
cookie flag is weakened.

Verified in a real browser (see `HOSTED_SECURITY_CHECKS.md`): the rewrite
carries `Range` requests through unchanged (`206` + correct `Content-Range`),
and a real `<video>` element loads metadata and seeks. Private responses
carry `Cache-Control: private, no-store` both from the API and from a
`vercel.json` header rule, so no assessment data can enter a shared edge
cache.

The rewrite is scoped to `/api/*` only: static assets and the client-side
`#/verify/:id` hash route are untouched.

**Android does not use this path** — it talks to Railway directly over
HTTPS, so large evidence uploads never traverse Vercel.

## 5. Evidence storage on Neon Object Storage

`server/app/storage.py` gains an `S3Storage` backend alongside the unchanged
`LocalDiskStorage`, chosen by `STORAGE_BACKEND` through `get_storage()`.
`STORAGE_BACKEND` defaults to `local`, so Docker Compose, the offline/LAN
deployment and the whole existing test suite behave exactly as before and
need no cloud credential.

### The append problem

S3 objects are immutable: there is no append, and PARAKH's resumable upload
protocol appends a 1 MiB chunk at a time. Two obvious approaches both fail:

* re-uploading the whole growing object per chunk is O(n²) — a 120 MB video
  would move ~7 GB;
* a part-per-chunk multipart upload is rejected by S3, which requires every
  part except the last to be **at least 5 MiB**, while PARAKH's chunks are
  1–2 MiB.

So each chunk is PUT as its own small, immediately durable staging object
under `{key}.staging/{seq:08d}`, and `finalize()` coalesces those into the
single object at `{key}` with one multipart upload that buffers them into
≥5 MiB parts. Each byte is uploaded once during the upload and re-written
once at completion — never per chunk. Zero-padded sequence numbers sort
lexicographically in upload order, so a plain `list_objects_v2` returns the
chunks correctly ordered.

Consequences that matter operationally:

* an API restart mid-upload loses nothing — every acked chunk is already a
  durable object, and the client resumes from the session's
  `next_chunk_index` as before;
* memory is bounded (one part plus one read block), not proportional to the
  object;
* a failed completion aborts the multipart upload but **keeps** the staging
  objects, so the client can retry `complete()` and succeed;
* `delete()` removes staging objects too, so an abandoned or expired session
  leaves no orphaned, billable objects.

Chunk-index validation, replay idempotency and out-of-order rejection are
**not** reimplemented in the storage layer — `routers/uploads.py` already
enforces them against the upload-session row under a row lock, and that
stays the single source of truth for both backends.

### Neon specifics

* **Path-style addressing only.** boto3 would otherwise default to
  virtual-hosted style for a custom endpoint and send requests to
  `{bucket}.{endpoint}`, which does not resolve.
* The credential's `token_id` is the S3 **access key id** and
  `s3_secret_access_key` is the secret. Credentials are scoped
  `storage:read` + `storage:write` only.
* Buckets are **private** on creation; an anonymous GET returns **403**
  (verified).

### Worker and serving

`worker.py` no longer instantiates `LocalDiskStorage` directly. ffmpeg and
ffprobe need real file paths, so cloud mode downloads the object to an
isolated temporary file via `storage.local_path()` — a no-op passthrough on
local disk, and a bounded temp download on S3 that is always removed on the
way out, success or failure. Only one evidence item is ever resident.

`routers/evidence.py` keeps Starlette's `FileResponse` (and its native
RFC 7233 handling) for the local backend, and proxies a ranged stream for
S3. Evidence is deliberately **proxied, never redirected to a presigned
URL**: a presigned URL is a bearer credential in a query string that would
bypass the router's authorization check entirely, land in browser history
and logs, and stay valid for its whole TTL regardless of whether the
assessor still has access.

## 6. Free-tier budget

| Provider | Plan | Entitlement | Observed |
|---|---|---|---|
| Neon | **Free** (ongoing) | 100 projects, 5 GB object storage + 5 GB egress per project | 1 project, 2 branches, 2 buckets; well inside limits |
| Vercel | **Hobby** (ongoing) | static hosting + rewrites | 1 project, static build |
| Railway | **Trial** (temporary) | **one-time $5, expires 30 days from issue** | $0.0035 used; $4.996 left |

Measured Railway usage over the first hour of both services running:

| Service | CPU (avg vCPU) | Memory avg | Memory max | Limit |
|---|---|---|---|---|
| `api` | 0.00273 | 95.7 MB | 208 MB | 1 GB |
| `worker` | 0.00117 | 44.7 MB | 90 MB | 1 GB |

At Railway's metered rates ($20/vCPU/month, $10/GB RAM/month) that is
**roughly $1.50/month** for both services. Memory peaks at about a fifth of
the 1 GB limit, so there is no OOM-restart risk at this workload.

> **The binding constraint is the calendar, not the credit.** Railway's $5
> is a one-time **trial** credit that expires **30 days from issue**, not an
> ongoing free tier. At ~$1.50/month the credit itself would last months,
> but it lapses first. Railway's ongoing **Free** plan grants about
> **$1/month in non-rollover credit**, which does not fund two always-on
> services continuously. After the trial window, keeping this deployment up
> 24/7 requires the $5/month Hobby plan — an explicit owner decision, not
> something this deployment assumes.
>
> No payment method is attached to the Railway account.

Levers if the credit needs to stretch: enable `sleepApplication` on `api`
(cold starts, and it must stay off for `worker`, which would otherwise stop
processing jobs), or combine both processes into one supervised service
(roughly halves RAM cost, at the cost of crash isolation).

## 7. Repeatable redeployment

### Dashboard (after UI/UX changes)

```sh
cd apps/dashboard
vercel deploy --prod            # uses vercel.json + the stored VITE_API_BASE_URL
```

`vercel.json` holds the `/api` rewrite, so a redeploy cannot silently lose
it. Git auto-deploy is **not** connected — deploys are explicit, so an
unfinished branch cannot reach the hosted environment.

### Backend

```sh
cd <repo root>
railway up --service api --ci
railway up --service worker --ci
```

Environment changes: `railway variable set KEY=value --service api`, or
`railway variable set --stdin KEY --service api` for a secret. Changing a
variable triggers a redeploy unless `--skip-deploys` is passed.

### Migrations (operator machine, direct connection)

```sh
cd server
DATABASE_URL="<Neon DIRECT/unpooled URL>" APP_ENV=staging \
  CORS_ALLOW_ORIGINS=https://parakh-dashboard-five.vercel.app \
  REPORT_SIGNING_PRIVATE_KEY=<the stable key> \
  python -m alembic upgrade head
```

### Switching the backend from `staging` to production (`main`)

Six variables on **both** services, then redeploy both:

```
DATABASE_URL          -> main branch POOLED connection
S3_ENDPOINT_URL       -> https://br-divine-leaf-b31f8cke.storage.c-4.ap-southeast-1.aws.neon.tech
S3_BUCKET             -> parakh-evidence
S3_ACCESS_KEY_ID      -> a credential issued on the main branch
S3_SECRET_ACCESS_KEY  -> "
S3_REGION             -> ap-southeast-1 (unchanged)
```

`main` is already migrated and pack-imported, so no further setup is needed.
Provision a real assessor on it first:

```sh
PROVISION_ASSESSOR_PASSWORD=... python -m server.app.provision_assessor \
  --email you@yourorg.example --display-name "Your Name"
```

Never run `python -m app.seed` against it — that creates demo workers and
sample assessments.

### Rollback

* Railway: `railway deployment list --service api`, then redeploy a known
  good deployment (previous images are retained).
* Vercel: `vercel rollback` or promote an earlier deployment.
* Database: Neon branches support point-in-time restore; a schema rollback
  is `alembic downgrade <revision>` over the direct connection.

### Android rebuild

```sh
cd apps/android
./gradlew :app:assembleRelease \
  -PreleaseSyncBaseUrl=https://api-production-c626.up.railway.app \
  -PRELEASE_STORE_FILE=... -PRELEASE_STORE_PASSWORD=... \
  -PRELEASE_KEY_ALIAS=... -PRELEASE_KEY_PASSWORD=...
```

Omitting the four signing properties produces a **debug-signed** APK with a
loud Gradle warning — fine for testing, never for distribution.

### Keys and backups

* `REPORT_SIGNING_PRIVATE_KEY` and `JWT_SECRET` live only in Railway's
  variable store and the operator's gitignored `.env.deploy`. Back the
  signing key up somewhere durable: losing it means no new report can be
  signed under the same `key_id`, and rotating it invalidates existing
  signatures unless the old public key is moved to
  `REPORT_SIGNING_KEY_HISTORY`.
* The Android release keystore (once created) must be backed up
  independently — losing it prevents updating an already-distributed app.
* Neon Free includes point-in-time restore; object storage is not
  automatically backed up, so evidence worth keeping should be exported
  deliberately.

## 8. Local and offline deployment are unchanged

`STORAGE_BACKEND` defaults to `local`, no cloud variable is required, and
`boto3` is only imported when the S3 backend is actually constructed. The
offline Docker Compose stack was re-verified after all of the above: the API
reports `LocalDiskStorage`, `/health` returns
`{"status":"ok","database":"ok","storage":"ok"}`, no `S3_*` variable exists
in the container, and the full 22-check P6/P7 end-to-end smoke test passes.
See `HOSTED_E2E_REPORT.md` §4.
