# Open-access workflow implementation review

Review date: 2026-10-17. Base: latest `main`,
`f02a9aaf3ddded50cadb57abbcb70b30ad59a9c7` (PR #12). The original working tree
was clean before fetching, switching to `main`, and fast-forward pulling.
All implementation changes remain **uncommitted** for the owner's review.
No push, merge, cloud deployment, secret installation, key rotation, cloud data
deletion, region move, or staging-to-production cutover was performed.

Operations, configuration, rollback and first-push verification:
[Open access release guide](../deployment/OPEN_ACCESS_RELEASE.md).
Source review: [complete modified-file inventory](OPEN_ACCESS_CHANGED_FILES.md).

## What changed

| Area | Existing behavior found | Implementation for review |
|---|---|---|
| Android registration | Phone/PIN intake; missing durable full name; sync fallback named candidates `Worker` | Required name, validated Indian mobile, security PIN/confirmation; durable private identity and optional public-name consent; atomic idempotent enrollment queued until sync |
| Local protection | SQLCipher, Keystore, signed manifests and encrypted vault already working | Salted PBKDF2-HMAC-SHA256, 600,000 iterations; encrypted verifier/profile; persistent lockout; PIN gate on foreground/recreation; forgotten PIN erases local drafts before new onboarding |
| Dashboard | Authenticated organizational queue | Public submitted-assessment projection, real empty state, 15-second refresh, consented name or pseudonym; original private app retained for offline deployments |
| Reviewer actions | JWT/roles and existing scoring/P7/report services | Separate assessment/revision/action-scoped email-code capabilities, operator allowlist, CSRF, expiry and rate limits; confirmation dialogs; actual actor snapshots and audits; no permanent reviewer account |
| Reports and evidence | Private storage, human scoring, Ed25519 PDFs, QR verification | Same services and storage; identity declaration and verification status added; only safe report availability/outcome/verification exposed publicly |
| Data | Historical staging fixtures; provenance not independently reverified | Additive Alembic migration marks historical rows legacy/no consent, excluding them from public lists without deleting anything |
| Hosting | Manual CLI deployments; Railway services have no Git source | One CI-gated release workflow, exact current main SHA, serialized migration/deployment, pinned existing service IDs and staging boundary, live source/worker health checks |
| Android delivery | Installed native APKs require explicit updates | Separate post-CI APK workflow; release checks, version and signing receipts; unsigned artifact when approved signing material is absent |

The original JWT, password hashing, roles, private routes, report key, upload
protocol, scoring rules and reassessment history remain. Account-free actions
use adapters with explicit authorization; `require_assessor` was not disabled.
The PIN never enters an enrollment body, signed manifest or evidence envelope.

Account-free reassessment responses preserve the old integer contract:
`requested_by_id=0` means no organizational account, while the database foreign
key is null and the real reviewer identity is in private snapshots/audits. This
keeps already-installed clients able to parse worker updates. Rollback builds
must retain this compatibility reader once such records exist.

## Verification

| Check | Result / reproducible evidence |
|---|---|
| Full backend suite, real local PostgreSQL | **318 passed**; `pytest server/tests -q`; final log `/tmp/parakh-open-backend-tests.log` |
| Release and offline tooling | **30 passed**; `pytest tools/tests -q`; includes fail-closed provider preflight and exact-commit upload context without untracked credentials |
| Android JVM regression | **192 passed**, zero failures/skips across matcher, budget, media, seal, quality, hands and app |
| Android lint and unsigned HTTPS release | **PASS**; debug/release lint and P4/P5/P6 release-hardening tasks; `/tmp/parakh-open-android-tests.log` |
| Connected physical OnePlus QA app | **37 passed** together; registration, wrong PIN, lockout/reopen, Activity recreation, forgotten-PIN erasure, real-name enrollment, interrupted sync, worker updates, migrations, EN/HI declaration, sealing, encryption and P8 inference/WorkManager; `/tmp/parakh-open-device-tests.log` |
| Public Playwright workflow | **7 scenarios passed** against the isolated real PostgreSQL/API stack; `/tmp/parakh-open-browser-tests.log` |
| Preserved private P10 Playwright workflow | **21 checks passed** against the isolated offline stack; `/tmp/parakh-open-private-browser-tests.log` |
| OpenAPI and Android language parity | **PASS**; exported contract fresh, 488 nonempty EN/HI values, 26 declaration IDs |
| Offline loaded-image bundle | **PASS**; isolated stack starts with `--no-build --pull never`; `/tmp/parakh-open-offline-verify.log` |
| Existing offline P6/P7 lifecycle | **22 checks passed** including immutable historical evidence, targeted recapture, signing, public verification and tampering detection; `/tmp/parakh-open-offline-smoke.log` |

Browser review/signing tests replace only email transport in a separate guarded
loopback test server. Its code-retrieval endpoint is absent from the product app.
These tests do **not** establish live SMTP delivery. Device tests ran only in
the separate `.p8validation` application; the installed candidate application
was not cleared or replaced. Existing CameraX field/performance evidence was
preserved; this run does not claim a new human usability study or device-tier
performance result.

The offline verification used current application files layered onto cached
dependency images because registry access was unavailable. A clean dependency
image rebuild and actual GitHub CI remain to be verified after the owner's push.
Local fixtures and any resets were confined to isolated test databases/volumes.

## Hosted blockers and audit

1. **Reviewer delivery unavailable.** No usable runtime SMTP account/verified
   sender and authorized reviewer list were available. Creating a free sender
   was authorized, but available integrations cannot provision its credentials or
   satisfy account/sender ownership verification. Signing/scoring fail closed
   until this is configured; self-declared identities receive no signing power.
2. **Deployment secrets not installed.** Owner approval was received. The active
   GitHub CLI account has write access but lacks repository administration;
   environment reads returned 404 and subsequent requests failed connectivity.
   The connected owner integration exposes no Actions secret-management tool.
   An owner/administrator must complete the approved configuration.
3. **Cloud audit incomplete.** Railway API/worker source, root, Dockerfile,
   start commands and absence of migration hooks were read. Both report region
   `iad`; it was preserved. Worker variables confirm Neon staging/private bucket
   and presence of its signing key. API variable reads, Vercel Git-link readback,
   direct SQL inventory of both Neon branches and live health were unavailable.
   The release preflight refuses missing/drifted settings before migration.
4. **Android signing unavailable.** No approved release keystore was supplied;
   no official signing identity was generated or substituted.
5. **No real push-triggered release yet.** Creating YAML and local tests cannot
   verify Vercel, either Railway service, Neon migrations or CI artifact delivery.

Required GitHub environment `hosted-staging` secrets:
`RAILWAY_TOKEN`, `VERCEL_TOKEN`, `NEON_DIRECT_DATABASE_URL` (direct **staging** URL).
Runtime SMTP variables and Android signing secret names are listed in the
[operations guide](../deployment/OPEN_ACCESS_RELEASE.md).

No deletion list is proposed: provenance of existing Neon data is unverified.
Both branches and all objects remain. Audit exact IDs and object references,
verify recoverability, and request separate approval before any future cleanup.
The deployed backend is never silently switched to Neon `main`.

## APK available for review

Local artifact: `apps/android/app/build/outputs/apk/release/app-release-unsigned.apk`.
Version code **2**, version name **0.7.0-open**, API endpoint
`https://api-production-c626.up.railway.app`.

SHA-256: `087da36c07a18ec8f701cfcb8ba4f1504050f520de472d029ebb12dd363a5063`.
Signing identity: **none**, explicitly unsigned and non-installable. Receipt:
`android-release-receipt.json` (ignored). Its source SHA identifies the base
commit and `source_tree_dirty=true` records the uncommitted implementation.
The post-push workflow builds the actual pushed SHA and records its identity.

An installed real APK updates only through an approved signed APK with the same
application ID/signing identity and a higher version code. Follow the operations
guide's installation steps; never uninstall genuine candidate data to bypass a
signature mismatch. Git pushes update neither an installed APK nor its local data.

## Acceptance table

Functional PASS entries below describe the local implementation and tests.
They do not assert that the unpushed code is already live.

| Requirement | Status | Evidence |
|---|---|---|
| Name + phone + PIN registration | PASS | Physical registration, encrypted profile, validation, wrong-PIN and erasure checks |
| No online candidate signup | PASS | Local onboarding; enrollment deferred to resumable sync |
| Offline assessment | PASS | Local draft/seal/inference regressions; existing capture architecture preserved |
| Real name synchronized | PASS | Physical sync asserts actual full name and phone; server persistence/retry tests |
| Dashboard opens without login | PASS | Real empty-state browser scenario |
| No dummy/demo data visible | PASS | Public projection excludes all legacy rows; no product seeding |
| Public summary access safe | PASS | Explicit safe schema, consent/pseudonym, private-route denial |
| Reviewer name/email capture | PASS | Browser confirmation/code dialog |
| Reviewer authorization | FAIL | Scoped authorization tests pass; usable hosted email delivery/list still missing |
| Rejection/reassessment history | PASS | Actor/reason/revision/task audits and P7 concurrency/history tests |
| Signed report integrity | PASS | Existing Ed25519 bytes, identity statement, QR and tamper tests |
| Private evidence remains protected | PASS | Anonymous access rejected; storage authorization retained |
| Backend regression tests | PASS | 318 tests |
| Android tests | PASS | 192 JVM + 37 physical; lint and release checks |
| Playwright E2E | PASS | Seven public scenarios + 21 original private P10 checks |
| Offline Docker regression | PASS | Loaded-image no-pull health and 22 P6/P7 checks |
| Automatic Vercel deployment | NOT VERIFIED | Workflow prepared; secrets and actual push-triggered release pending |
| Automatic Railway API deployment | NOT VERIFIED | Same gate; pinned existing API service |
| Automatic Railway worker deployment | NOT VERIFIED | Same gate; pinned existing worker and heartbeat check |
| Safe Neon migration integration | NOT VERIFIED | Real PostgreSQL migration/idempotency passed; hosted direct connection pending |
| Automated Android APK build | NOT VERIFIED | Local unsigned artifact built; GitHub trigger and approved signing pending |

## Owner's next steps

1. Review the uncommitted changes and the modified-file inventory alongside this
   report. Complete owner/admin staging secrets and usable reviewer delivery.
2. Verify provider preflight settings and both Neon inventories without deleting
   data. Retain staging. Configure the Android signing environment only with the
   existing approved identity, or expect an unsigned CI artifact.
3. Manually commit and push to `main`. Follow the release guide's exact first-push
   verification steps, including CI SHA, migration receipt, both Railway deployment
   IDs, Vercel version stamp and recent worker heartbeat.
4. Mark automatic deployment accepted only after that real workflow succeeds;
   separately validate staging uploads/playback, report persistence across service
   restart and actual reviewer email delivery. Production cutover needs separate
   owner approval.
