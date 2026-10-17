# Open access workflow and coordinated releases

This implementation starts from `main` at `f02a9aa` (PR #12 merged). Changes
are uncommitted. No cloud deployment, secret installation, database cutover,
cloud record cleanup or key rotation was performed.

## Candidate registration and security PIN

Android collects full name, an Indian mobile number (10 digits beginning
6–9), a four-digit **security** PIN and confirmation. Public name sharing is
optional and unchecked. The consent text explains that anyone can see a shared
name, status and outcome; otherwise the public dashboard uses `Candidate #id`.
The phone stays private. Registration and the declaration/capture workflow
require no internet, account, OTP or externally issued worker ID.

`CandidateSecurity` persists the profile in Keystore-backed encrypted preferences
even before a draft exists. Room schema 7 adds name, phone, consent and a random
256-bit enrollment secret to the existing SQLCipher-encrypted draft. Migration
6→7 preserves old drafts, sealed evidence, upload receipts and reassessment state.
The PIN never enters Room, a manifest, an evidence envelope, a network request,
saved Compose state or logs. Only a salted PBKDF2-HMAC-SHA256 verifier (600,000
iterations, random 32-byte salt) is stored in encrypted preferences. PIN derivation
runs off the UI thread. This short PIN controls local UI access; the Keystore,
SQLCipher and existing encrypted evidence vault provide device storage protection.
It is not cloud authentication or a defence against a fully compromised device.

Restart and background/resume require unlocking. Failed attempts persist across
reopening: after five failures the delay begins at 30 seconds and doubles, up to
24 hours. A successful unlock resets the counter. Screenshots and app-switcher
previews are blocked with `FLAG_SECURE`. Forgotten PIN has no identity or evidence
recovery: after explicit confirmation, local assessment files and sync credentials
are removed before registration can start again. Cloud records remain untouched.
Old drafts without a verifier require Android device-credential confirmation before
setting a PIN, or explicit local erasure. An old missing name cannot be reconstructed
automatically; historical records stay outside public browsing.

The first synchronization calls `POST /workers/enroll`, carrying the real name,
private `+91` phone, consent, device ID, client assessment UUID and random enrollment
secret. This atomic transaction creates both identity and assessment. Retries prove
the device secret and return the same assessment/capability, including after a lost
bootstrap acknowledgement. Server stores only the enrollment secret hash; the
assessment token is deterministically derived from the random device secret and
client assessment UUID, with only its hash persisted. Tokens remain assessment-scoped.
The legacy bootstrap contract remains available for older clients and old drafts.

## Public dashboard and reviewer authority

Hosted dashboard defaults to public browsing, with no login or demo switch. It
polls `/public/assessments` every 15 seconds while visible, shows an honest empty
state, and supports bounded ID pagination. Only submitted `candidate-v1` enrollments
are included. Legacy/unknown historical rows are excluded by default, without
deleting or guessing the provenance of any record. No fixtures are auto-seeded.

Public models contain assessment ID, consented name or pseudonym, QP code,
submission time, task evidence counts, status, revision and report availability.
They never contain phone, PIN/verifier, enrollment secret, worker token, object key,
recording, private remarks, assessor contact information or full report. Existing
public QR verification exposes the minimal integrity/outcome presentation. Signed
PDFs and evidence stay private in Neon; buckets must not be made public.

Reviewers use `/reviewer/*`, a separate adapter over the existing scoring,
reassessment and report services. Existing JWT, roles, password hashing, login,
CSRF and all private API authorization are retained. Reviewer sessions do not grant
access to those private APIs or to token administration. No permanent user/account
is created by a reviewer name/email declaration.

Operator permission and email ownership are separate checks. Set an exact reviewer
email allowlist and a working SMTP sender. Each code is random, expires after ten
minutes, permits five guesses, is hashed with server HMAC and can be redeemed once.
The session is a random capability stored hashed in PostgreSQL, delivered as an
HttpOnly cookie, expires in 15 minutes and is bound to one assessment and revision.
Mutations require a separate CSRF header. The allowlist is rechecked on every call.
Scopes distinguish review/scoring, rejection, reassessment and sign-off. Each
consequential action needs a fresh code and explicit dialog confirmation; its
capability expires in the same transaction as the decision. Private browser panels
are cleared on expiry. Email ownership is verified; the person's name remains
self-declared and professional competence is not verified by this mechanism.

Mail configuration (Railway API secure variable store):

| Variable | Purpose |
|---|---|
| `REVIEWER_ALLOWED_EMAILS` | Comma-separated exact authorized addresses |
| `REVIEWER_SMTP_HOST` | Existing operator-approved mail service |
| `REVIEWER_SMTP_PORT` | STARTTLS port, default 587 |
| `REVIEWER_EMAIL_FROM` | Sender permitted by that service |
| `REVIEWER_SMTP_USERNAME` | Sender login where required |
| `REVIEWER_SMTP_PASSWORD` | Private app password or SMTP credential |

**Blocker:** no genuinely usable mail sender was available/configured in this
session. The implementation fails closed with 503 and disables review controls
until configured. Local tests substitute the transport in a loopback-only test
server; that endpoint is never installed in the production application. An existing
free SMTP account may be usable, but its quota, TLS support and delivery must be
confirmed by the owner; no paid mail provider or automatic account was created.

Scoring retains 0–3, NOT_OBSERVABLE remarks, critical-PC rules, computed profiles,
override reasons, optimistic versions and assessment row locks. Every criterion
must be human-confirmed before account-free sign-off. Targeted reassessment uses
the existing revision mechanism and locks the same assessment row as signing.
Rejection and reassessment record name, email, verification status, time, reason,
revision and exact task codes in private snapshots and append-only audit entries.
For installed legacy Android clients, `requested_by_id` remains an integer on the
wire: reserved value `0` means an account-free reviewer, never a user account or
authorization. The database foreign key is null and the actual actor is recorded
in the private identity snapshot/audit. No permanent account is created.
Reports retain Ed25519 signing of immutable stored PDF bytes and QR verification.
Their identity statement distinguishes email verification, self-declared name and
server signing. They remain assessor recommendations, **not official NCVET/MSDE
certificates**. Existing report bytes and keys are never changed.

## Abuse and free/trial capacity

Database-backed counters survive restarts and replicas. Enrollment is capped at
20 requests per source/hour and 100 globally/day; deployment defaults cap total
assessments at 200 and candidates at 300, and five new assessments per enrolled
candidate. Public summaries have 50-row pages (maximum 100), 600 global and 240
per-source requests/minute. Verification and email have additional rate limits;
email delivery is capped at 50 messages/day globally, ten/address and 20/source
per ten minutes. Do not trust caller-supplied forwarding headers. Configure trusted
proxies deliberately if distinct client address attribution is required; a shared
proxy address makes the source limit conservative.

Existing per-task and 120 MiB assessment quotas remain. A PostgreSQL advisory lock
serializes deployment storage reservations. `PUBLIC_STORAGE_MAX_BYTES` defaults to
512 MiB of evidence plus upload reservations, including expired/aborted sessions
conservatively until an operator reconciles them; completed manifest reservations
also count. Session counts are capped at 500/assessment and 5,000/deployment.
`PUBLIC_ENROLLMENT_MAX_ASSESSMENTS` can be adjusted explicitly by the operator.
These are application ceilings, not a provider billing guarantee: thumbnails,
reports, request processing, egress and existing records also consume allowance.
No plan upgrade, region move or additional hosted runtime service is requested.
Retain provider spend limits and check remaining trial credit before enabling
releases. Two always-running Railway services are not guaranteed indefinitely ₹0.

## Hosting audit and environment boundary

`infra/hosting-target.json` pins the existing project, environment, service IDs,
public URLs and **Neon staging** endpoint/bucket. Railway's environment is named
`production`, but that label must not be confused with the Neon `main` branch.

Read from Railway settings during this session: both services have `source.repo=null`,
use repository-root context with `server/Dockerfile`, and no pre-deploy migration
command. API command is `uvicorn app.main:app --host 0.0.0.0 --port 8000`; worker
command is `python -m app.worker`. Both reported `multiRegionConfig.iad`, which
differs from the earlier Singapore documentation. No region setting was changed.
Vercel project inspection confirmed existing project ID, root `null` (CLI sends
`apps/dashboard` as project root), Vite build and `dist` output.

Provider API, GitHub, live endpoint and direct Neon reads repeatedly failed DNS
resolution or timed out. A final read confirmed the worker's pooled Neon staging
hostname, `parakh-evidence-staging` bucket, staging storage endpoint, and configured
report-signing key (presence only). API variables remained unavailable. Current
Vercel Git linkage, both Neon datasets and current cloud health could not be read
back reliably. Other target metadata was recovered from existing gitignored local
deployment metadata, **not treated as a current provider audit**.
The release preflight rechecks them live and stops before migrations on mismatch.
Use `python tools/audit_open_access_hosting.py` with existing authenticated CLIs
and backend dependencies to repeat the read-only audit. It prints no secret values.

Historical synthetic cleanup plan: delete **nothing**. New migration assigns every
old row `provenance=legacy` and consent false. Re-run the read-only audit on both
branches, compare exact IDs/fingerprints and receipt evidence against historical
test logs, and retain unknown/potentially genuine records. Any later deletion
proposal must enumerate exact record IDs and private object keys in a protected
review artifact, verify backups/recoverability, and obtain explicit owner approval.
No staging/main branch is destroyed, and no automatic data cleanup is in migrations.

## Automatic deployment after the owner's push

There is one coordinated cloud release mechanism: `.github/workflows/release.yml`.
Do not also connect native Vercel/Railway Git auto-deployment. The workflow uses
GitHub's [`workflow_run`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
after the existing CI completes, and requires a successful same-repository push
to `main`, exact SHA still at the tip, and every required CI job successful,
including browser and offline verification. A concurrency group serializes releases.

Create the GitHub environment **`hosted-staging`** and configure these encrypted
environment secrets, after owner approval:

| Secret | Value source |
|---|---|
| `RAILWAY_TOKEN` | Project-scoped token for the existing Railway project/environment |
| `VERCEL_TOKEN` | Approved token permitted to deploy the existing project |
| `NEON_DIRECT_DATABASE_URL` | Existing **staging direct/unpooled** PostgreSQL URL, using `postgresql+psycopg` |

Do not put signing keys, JWT secret, S3 credentials, a pooled production URL or
Android signing material into workflow YAML. Runtime secrets remain in Railway.
The owner approved secure configuration of these three staging secrets. No secrets
were installed: the authenticated CLI account has repository write access but lacks
administration access to manage the protected environment; environment reads returned
404, and subsequent network reads failed. The connected owner GitHub integration
does not expose Actions secret-management tools. Authenticate the CLI as the owner
or have an administrator configure them. Deployment cannot succeed until these
secrets and provider access are configured. Environment protection may require
an owner release approval if that protection is enabled; choose this deliberately.

The release installs pinned Railway 5.70.0/Vercel 64.5.0 tools, verifies provider
settings and no conflicting native Git sources, validates the runtime DB/bucket
against the pinned staging target, then runs `tools/release_migrate.py`. That step
uses the direct connection, a session-level PostgreSQL advisory lock and Alembic
head comparison. At head it runs no upgrade/DDL; on a new revision only one release
can apply it. Migration failure stops application deployment. API and worker do
not migrate at startup. New schema `d42e17a98c01` expands existing tables without
publishing or deleting old records; application rollback retains that schema.

Next it exports the exact approved commit with `git archive`, adds the source SHA
stamp in that temporary directory, and uploads this repository-root build context
to the two **existing** Railway service IDs using
[`railway up`](https://docs.railway.com/cli/up). `--no-gitignore` includes the
generated stamp only in this clean exported context; untracked local credentials
never enter the archive. It then
polls deployment status, builds Vercel from `apps/dashboard` with
`VITE_API_BASE_URL=/api`, and deploys prebuilt output using the
[official Vercel CLI flow](https://vercel.com/kb/guide/how-can-i-use-github-actions-with-vercel).
`vercel.json` retains the same-origin `/api` rewrite. Hosted builds default to `/api`
if no build variable exists and never default to localhost. The release embeds
SHA stamps in API/worker and frontend, verifies healthy DB/storage plus a recent
worker heartbeat and same-origin compatibility, and records GitHub deployment
status and safe receipt artifacts. Failed health checks mark the release failed.
Raw variable/secret-bearing provider logs are not copied into public CI output.

First-trigger verification, performed by the owner:

1. Finish the read-only provider/branch audit; configure the three staging secrets
   with approval. Confirm no native source deploys and no provider pre-deploy
   migration hook. Keep Neon staging selected. Configure and test SMTP separately.
2. Review the complete diff, manually commit, and push that commit to `main`.
3. Confirm `CI` at the exact pushed SHA passes every job. Failed CI must create
   no successful release. `Release hosted staging` should then start automatically.
4. Inspect the release's deployment/migration receipts and existing provider
   deployment histories. Confirm API and worker IDs remain unchanged and both
   new deployments represent that SHA; no extra services or region changes.
5. Check `/health` and `/api/health` through the dashboard: `source_sha` and
   `worker_source_sha` must equal the pushed SHA, DB/storage must be `ok`.
   `/version.json` on Vercel must contain the same SHA. Test a real consented
   submission, private evidence playback and reviewer mail delivery on staging.
6. On a later approved commit without a schema change, `migration-result.json`
   must say `changed:false`; no DDL runs. Retain receipts for rollback.

**Acceptance remains NOT VERIFIED until an actual owner push completes all of this.**
Creating these YAML files or passing local tests does not establish automatic
deployment, provider credentials, delivery, persistence across cloud restarts or
live source compatibility.

## Android APK delivery

`.github/workflows/android-release.yml` separately runs after successful `main` CI
for that exact current SHA. It builds against the Railway HTTPS endpoint, runs
release lint and all existing P4/P5/P6 hardening tasks, and uploads a 14-day CI
artifact. Version code is `1000 + workflow run number`; version name includes the
commit SHA. The receipt records actual APK hash, code/name, source SHA and
certificate fingerprint. Existing installed APKs do not update from Git pushes.

Use GitHub environment **`android-release`**. Signing is optional only in the sense
that absent material yields an **unsigned, non-installable test artifact**. No
debug key is substituted and no official signing identity is generated.

| Environment secret/variable | Purpose |
|---|---|
| `ANDROID_RELEASE_KEYSTORE_BASE64` (secret) | Existing approved keystore bytes encoded for encrypted storage |
| `ANDROID_RELEASE_STORE_PASSWORD` (secret) | Existing store password |
| `ANDROID_RELEASE_KEY_ALIAS` (secret) | Existing approved alias |
| `ANDROID_RELEASE_KEY_PASSWORD` (secret) | Existing key password |
| `ANDROID_RELEASE_CERT_SHA256` (variable) | Approved certificate SHA-256 fingerprint to enforce |

Partial signing configuration fails. Supplied signing material must produce the
approved fingerprint and must not be an Android Debug certificate. The ephemeral
keystore is removed after build. No signing material was available in this session.
Download the authorized artifact from GitHub Actions, check its receipt/hash and
certificate, then install/update manually (`adb install -r approved-release.apk`
or Android's installer with user consent). Updates require the same application
ID/signing identity and a higher version code. Do not uninstall an existing genuine
candidate installation to bypass a signature mismatch. Unsigned artifacts cannot
be installed; use the explicitly isolated QA app for testing. No self-updater exists.

## Offline deployments and rollback

Docker defaults remain local PostgreSQL/private disk, with no Vercel/Railway/Neon,
SMTP or cloud secret requirement. The dashboard container defaults to the preserved
organizational/private UI (`DASHBOARD_ACCESS_MODE=private`), using the original
login and assessor roles. Optional public mode requires `DASHBOARD_ACCESS_MODE=public`;
it is never necessary for offline assessment/review. No visible product mode switch
or automatic fixture seeding was added. Local migration remains the Compose
one-shot dependency before API/worker startup.

On deployment failure, stop further releases and inspect provider protected logs
and the recorded previous deployment IDs. Restore previous successful Railway
deployments through their deployment history, or deploy a reviewed known-good
checkout to the same service IDs; `railway redeploy` alone redeploys the latest
deployment and does not select an arbitrary old version. Restore Vercel with
`vercel rollback <previous-deployment-url-or-id>`. Keep the expanded database schema,
unchanged private storage and stable report key. Never automatically downgrade
the database. Neon restore/cutover requires an explicit reviewed recovery plan.
After account-free reassessments have been created, a rollback target must support
their nullable reviewer foreign keys and the legacy wire marker. The pre-change
backend assumes every request has an account ID; use a compatibility-patched
rollback build rather than that older reader unchanged.

Production cutover remains a separate owner approval. Audit both branches and
bucket credentials, prepare/verify migrations and pack import on Neon `main`,
back up recoverable data, and approve the exact service-variable changes. Then
update the reviewed target file, production GitHub environment and direct URL
secret together; set both service DB/bucket variables to the approved production
branch while preserving signing keys. No code path silently falls back to `main`.
Future successful `main` CI releases use that reviewed environment configuration;
they do not repeat manual branch selection.
