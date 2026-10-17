# Hosted end-to-end test report

Every result below was produced by running against the **actual deployed
services** — Railway's API and worker, Neon's PostgreSQL and private object
storage, and the Vercel-hosted dashboard in a real browser. No API response
is mocked anywhere in this report.

| | |
|---|---|
| Source branch | `deploy/vercel-railway-neon` (based on `e53ecb3`) |
| API under test | `https://api-production-c626.up.railway.app` |
| Dashboard under test | `https://parakh-dashboard-five.vercel.app` |
| Database | Neon project `parakh`, branch **`staging`**, revision `b89e72c4d010` |
| Bucket | `parakh-evidence-staging` (private), `ap-southeast-1` |
| Browser | Playwright-bundled Chromium 1243, headless |
| Test data | Synthetic, created by the suites below, confined to the `staging` branch |

All hosted test activity ran against the **isolated `staging` Neon branch
and its own bucket**. The `main` branch — reserved for the team's real
assessments — is migrated and pack-imported but still has **zero**
transactional rows.

## 1. Backend regression (pre-flight, local)

Run before and after the cloud changes, against a real PostgreSQL 16:

| Stage | Result |
|---|---|
| Baseline on untouched P10 tree | **286 passed** (103 s) |
| After all cloud-storage changes | **300 passed** (100 s) — 286 original + 14 new |

Zero regressions. The 14 new tests are `server/tests/test_storage_s3.py`.

## 2. S3 storage adapter unit/integration tests

`server/tests/test_storage_s3.py`, 14 tests, against moto's in-process S3.
The one real-S3 rule moto does **not** enforce is multipart's 5 MiB minimum
part size — which is precisely the constraint that makes a naive
part-per-chunk upload fail in production — so that test asserts the part
sizes this code actually submits rather than trusting the mock to reject
them.

| Test | Result |
|---|---|
| write/read/delete round trip | PASS |
| missing key reports size 0 | PASS |
| append accumulates and is visible before finalize | PASS |
| every chunk durable immediately (a new client sees them all) | PASS |
| **12 × 1 MiB coalesced into parts ≥ 5 MiB** | PASS |
| single-chunk finalize skips multipart entirely | PASS |
| finalize idempotent on a replayed complete | PASS |
| delete removes staging — no orphans | PASS |
| failed multipart aborts but **keeps** staging for retry | PASS |
| inclusive HTTP Range semantics | PASS |
| ranges work before finalize too | PASS |
| `local_path()` materialises then always cleans up (incl. on exception) | PASS |
| corrupted object caught by SHA-256 | PASS |
| missing object reports absent rather than raising | PASS |

### Defect found and fixed by these tests

`copy_object` silently keeps the **source** object's metadata unless
`MetadataDirective="REPLACE"` is set. The single-chunk finalize path (which
every photo takes) was therefore storing evidence as
`binary/octet-stream` instead of its declared MIME type. Fixed in
`server/app/storage.py`.

## 3. Live Neon Object Storage checks

Run against the **real** `parakh-evidence-staging` bucket over the network —
real multipart semantics, real path-style addressing, real credentials. All
objects written were deleted afterwards (0 remaining under the test prefix).

| Check | Result | Detail |
|---|---|---|
| `probe()` proves the bucket is writable | PASS | |
| small object write/read/size | PASS | |
| **12 × 1 MiB → multipart with ≥ 5 MiB parts** | PASS | parts submitted: **5.0 MiB, 5.0 MiB, 2.0 MiB** |
| single-chunk photo finalize + correct MIME | PASS | |
| HTTP Range reads (video seeking) | PASS | |
| `local_path()` for ffmpeg, then cleanup | PASS | |
| interrupted upload resumes after a new client | PASS | |
| `finalize()` idempotent on replay | PASS | |
| `delete()` leaves no orphans | PASS | |
| missing object reports absent | PASS | |
| **anonymous access refused** | PASS | **HTTP 403** |

**11/11 passed.** The part sizes are the headline: real S3 would reject
1 MiB non-final parts, and the coalescing produced exactly the 5/5/2 MiB
split the design intends.

## 4. Full P6/P7 workflow — hosted

`tools/docker_e2e_smoke_p6.py`, **unmodified**, pointed at the Railway API.
The same 22-check suite that guards the local stack, now run against cloud
infrastructure. (A wrapper pre-resolves and caches DNS because *this
laptop's* resolver is unreliable — it does not alter the suite.)

| # | Stage | Hosted | Offline Docker |
|---|---|---|---|
| 1 | assessor login | PASS | PASS |
| 2 | worker self-registration is idempotent | PASS | PASS |
| 3 | resolve pinned QP code/version to a pack id | PASS | PASS |
| 4 | create assessment (draft) | PASS | PASS |
| 5 | upload a **real ECDSA-signed** manifest | PASS | PASS |
| 6 | sync-status: manifest received, items pending | PASS | PASS |
| 7 | T1 photo cross-checked against the verified manifest | PASS | PASS |
| 8 | deliberately WRONG hash for T2 rejected (409) | PASS | PASS |
| 9 | submit blocked until every declared item verified | PASS | PASS |
| 10 | correct-hash T2 completes the manifest | PASS | PASS |
| 11 | submit succeeds once the package is complete | PASS | PASS |
| 12 | assessment records the device's pinned public key | PASS | PASS |
| 13 | evidence is protected, playable and scoreable | PASS | PASS |
| 14 | audit log records sync actions with old/new score | PASS | PASS |
| 15 | audit log protected — worker token cannot read it | PASS | PASS |
| 16 | targeted reassessment of T2 only, with reason | PASS | PASS |
| 17 | T1 locked; T2 accepts a fresh upload session | PASS | PASS |
| 18 | v2 manifest re-declares T1 **by reference** | PASS | PASS |
| 19 | resubmit returns to `submitted`, fulfils the request | PASS | PASS |
| 20 | v1 T1 evidence and score remain **immutable** | PASS | PASS |
| 21 | re-review reopened PC; password-confirmed sign-off | PASS | PASS |
| 22 | public `/verify/{report_id}`; tampered copy fails offline verify | PASS | PASS |

**22/22 hosted. 22/22 offline.** Identical behaviour on both backends.

### Railway worker job processing

All jobs enqueued by the hosted run, read back from Neon:

| Job type | Status | Attempts | Count |
|---|---|---|---|
| `verify_evidence` | succeeded | 1 | 4 |
| `extract_metadata` | succeeded | 1 | 4 |
| `generate_thumbnail` | succeeded | 1 | 2 |

Every job succeeded on the **first** attempt — no retries, no stale-job
recovery needed. `verify_evidence` succeeding proves the worker re-read each
stored object out of the private Neon bucket and re-hashed it.

### Rows created in Neon `staging` by the hosted runs

`assessments` 5 · `assessment_tasks` 10+ · `evidence_items` 4+ ·
`device_manifests` 3 · `jobs` 10 · `signed_reports` 1 ·
`assessment_criterion_scores` 11 · `reassessment_requests` 1 ·
`audit_log` 37 · `upload_sessions` 7 · `upload_chunks` 7 · `users` 2

## 5. Real-media hosted check (the decisive storage proof)

The suite in §4 uploads **synthetic** bytes, so ffprobe/ffmpeg legitimately
report `unavailable` for them — which is indistinguishable from a *broken*
S3 download. (The offline stack produces the identical `unavailable` for the
same inputs, confirming parity but not correctness.)

This check removes the ambiguity: a real JPEG and a real **7.3 MiB** H.264
MP4 are pushed through the hosted API in 1 MiB chunks, and the Railway
worker must come back with actual pixel dimensions, an actual duration and a
real generated thumbnail. Those values can only exist if
`S3Storage.local_path()` genuinely materialises the object from the private
Neon bucket for ffmpeg.

| Check | Result | Detail |
|---|---|---|
| signed manifest accepted | PASS | |
| real photo uploaded, hash verified server-side | PASS | 1 chunk |
| real video uploaded in multiple chunks, hash verified | PASS | **8 chunks**, 75.5 s → forced the ≥5 MiB coalesce |
| worker extracted **real photo dimensions** | PASS | **1280×720** |
| worker extracted **real video dimensions** | PASS | **640×480** |
| worker extracted a plausible duration | PASS | **6000 ms** |
| worker **generated a thumbnail** into the private bucket | PASS | `completed` |
| photo content served with exact bytes | PASS | HTTP 200, 34 877 B |
| private evidence not shared-cacheable | PASS | `private, no-store` |
| generated thumbnail served as JPEG | PASS | HTTP 200, 33 443 B |
| video Range returns **206 Partial Content** | PASS | |
| 206 body is exactly the requested bytes | PASS | 1024 B |
| `Content-Range` reports the true object size | PASS | `bytes 0-1023/7618288` |
| mid-file seek returns correct bytes (scrubbing) | PASS | 2048 B |
| unsatisfiable Range rejected | PASS | **416** |
| evidence refused without a valid session | PASS | **401** |

**16/16 passed.**

## 6. Browser end-to-end on the hosted dashboard

`apps/dashboard/e2e/hosted-cloud.mjs` (new; adapted from the existing e2e
structure to the hosted endpoints). Real Chromium against the real Vercel
deployment, real Railway API, real Neon staging data.

**31 passed, 0 failed.** Full list in `HOSTED_SECURITY_CHECKS.md` §2–§4;
functional highlights:

| Check | Result | Detail |
|---|---|---|
| dashboard loads over HTTPS from Vercel | PASS | HTTP 200 |
| production bundle contains **no** localhost API URL | PASS | |
| bundle targets the same-origin `/api` proxy | PASS | |
| login through the `/api` rewrite | PASS | HTTP 200 |
| authenticated `/auth/me` with the cookie alone | PASS | HTTP 200 |
| assessment queue loads | PASS | |
| private photo loads through the proxy | PASS | 34 877 B |
| worker-generated thumbnail renders through the proxy | PASS | 33 443 B |
| **Range request survives the Vercel rewrite** | PASS | 206, `bytes 0-1023/7618288` |
| **a real `<video>` element loads metadata** | PASS | **640×480, dur 6 s** |
| signed report PDF downloads through the proxy | PASS | 42 447 B, magic `%PDF-` |
| public `/verify/{id}` works unauthenticated | PASS | HTTP 200 |
| public hash-route page renders for an **anonymous** visitor | PASS | 687 chars |
| verification page shows the report id | PASS | |
| logout, then session rejected | PASS | 200 → 401 |

Console/network observations: 0 failed requests of consequence, **0 5xx API
responses**. Two `net::ERR_ABORTED` entries are the `<video>` element
correctly abandoning the full download after `preload="metadata"`; the 404s
are the deliberate `/config.json` runtime-config probe, which is documented
as a graceful best-effort fallback (it only exists for the Docker image).

### Test defects corrected during this run

Three initial failures were faults in the new test, not the deployment, and
are recorded for honesty:

1. CSRF was first probed with `POST /auth/logout`, which takes no
   `get_current_user` dependency (it only clears cookies) and is therefore
   CSRF-free **by design** — it passed trivially and destroyed the session
   mid-run. Re-pointed at `POST /assessments/{id}/start-review`, a genuine
   state-changing endpoint behind `get_current_user`, where `auth.py`
   actually enforces double-submit.
2. Media checks iterated `/queue`, which cannot reach a signed-off (already
   left) or draft (not yet entered) assessment. Changed to enumerate
   assessments directly, preferring one with a worker-processed video.
3. `page.goto()` to a URL differing only by `#fragment` is a same-document
   navigation and returns `null`; the hash-route check now asserts on
   rendered content.

## 7. Android

Physical device: **OnePlus 13R (CPH2691 / OP5D3BL1), Android 16, API 36,
arm64-v8a**, connected and authorised over USB (`adb` serial `d34cebae`).

Toolchain used: JDK 25 (Android Studio's bundled JBR), Android SDK Platform
36 + Build-Tools 36.0.0 + Platform-Tools 37.0.1, Gradle 9.7.1, AGP 9.4.1.

### Unit tests (host)

| Stage | Result |
|---|---|
| Kotlin matcher parity (`core:mapping`) | **13 tests, 0 failures** |
| Full Android unit suite (`./gradlew test`) | **190 tests, 0 failures** |

Per-module: `app` 88 · `core/seal` 24 · `assist-quality` 23 · `media` 21 ·
`core/mapping` 13 · `core/budget` 12 · `assist-hands` 9.

### Builds

| Artifact | Result |
|---|---|
| `app-debug.apk` | built, 91.55 MB |
| `app-release.apk` | built, 67.67 MB (R8 minify + resource shrink enabled) |
| Bundled assistance model verification | PASS — official origin/hash, licence evidence and pinned dependency validated |

### Release endpoint — the actual Railway API, no placeholder

Built with `-PreleaseSyncBaseUrl=https://api-production-c626.up.railway.app`.
Read back from the generated release `BuildConfig`:

| Field | Release | Debug |
|---|---|---|
| `P6_RELEASE_SYNC_BASE_URL` | **`https://api-production-c626.up.railway.app`** | — |
| `P6_TEST_ONLY_SYNC_ENDPOINT_OVERRIDE_ENABLED` | `false` | `true` |
| `P6_TEST_ONLY_DEFAULT_SYNC_BASE_URL` | `""` | (overridable, see below) |
| `P4_TEST_ONLY_CEILING_ENABLED` | `false` | `true` |
| `P5_TEST_ONLY_FORCE_OPTIMIZE_ENABLED` / `_DEBUG_EXPORT_ENABLED` | `false` / `false` | `true` / `true` |
| `DEBUG` | `false` | `true` |

All nine of the repository's own release-hardening Gradle verifications pass
— see `HOSTED_SECURITY_CHECKS.md` §8.

**Signing: the release APK is DEBUG-signed** (`CN=Android Debug`), the
build's own loudly-warned fallback, because no keystore or `RELEASE_*`
signing material exists. Installable for testing, **not distributable**. No
replacement keystore was generated — that is an owner decision.

### Instrumented tests on the physical device

`./gradlew :app:connectedDebugAndroidTest` — **37 tests, 36 passed, 1
assumption-skip (97%)**:

| Class | Tests | Failures | |
|---|---|---|---|
| `SealOrchestratorInstrumentedTest` | 8 | 0 | P5 seal state machine |
| `SqlCipherAndPermissionsTest` | 4 | 0 | SQLCipher + permission policy |
| `AssistanceUiInstrumentedTest` | 4 | 0 | |
| `SyncRepositoryInstrumentedTest` | 4 | 0 | resumable sync |
| `AssistanceIntegrationInstrumentedTest` | 3 | 0 | |
| `DeclarationContractAndSafetyTest` | 3 | 0 | |
| `AppDatabaseMigrationTest` | 2 | 0 | Room migrations |
| `AssistanceUploadInstrumentedTest` | 1 | 0 | **real upload + targeted reassessment** |
| `AssistanceWorkManagerInstrumentedTest` | 1 | 0 | WorkManager |
| `OfflineAirplaneModeTest` | 1 | 0 | offline matching |
| `HindiFlowTest` | 1 | 0 | Hindi UI flow (automated) |
| `AppropriateMatchFlowTest` / `PartialMatchFlowTest` | 1 / 1 | 0 / 0 | |
| `AssistanceMigrationInstrumentedTest` | 1 | 0 | |
| `WorkerUpdatesRepositoryInstrumentedTest` | 1 | 0 | |
| `EvidenceCaptureFlowTest` | 1 | **1** | assumption-skip, see below |

Two harness problems had to be solved to get the sync tests to run on a
real phone, and both are now reusable:

* `AssistanceUploadInstrumentedTest` requires `p8ApiBaseUrl` on **port
  18008** and initially failed `Retryable(NETWORK_UNAVAILABLE)`. The debug
  build hardcoded `http://10.0.2.2:8000` — the **emulator-to-host** alias,
  unreachable from a real device. `debugSyncBaseUrl` is now overridable with
  `-PdebugSyncBaseUrl=` (mirroring the existing `releaseSyncBaseUrl`
  pattern), and `adb reverse tcp:18008 tcp:8000` tunnels the phone's own
  localhost to the host's running stack — no LAN IP or second backend
  needed. With the harness's documented test assessor provisioned, it
  **passes**, exercising real evidence upload and targeted reassessment on
  the device.

### The one remaining failure

`EvidenceCaptureFlowTest.real_photo_capture_add_replace_remove_roundtrip`
throws `AssumptionViolatedException` — a JUnit **skip** that AGP's Unified
Test Platform reports as a failure:

> Skipping: this device's OS build does not allow unattended runtime
> permission granting (android.permission.CAMERA) — real capture is proven
> by the manual device gate instead.

OxygenOS silently refuses `pm grant` for CAMERA (the test explicitly checks
the real permission state rather than trusting the shell's exit text).
Pre-granting from the host does not help, because the instrumentation APK is
installed and uninstalled around each run. The project's own answer to this
is the manual physical-device gate (`docs/gates/P4.md`,
`docs/gates/P6_physical_device_2026-10-14.md`). **Not a regression, and not
caused by any change here.**

### A real pre-existing defect found and fixed

Three instrumented tests (`SqlCipherAndPermissionsTest`,
`AppropriateMatchFlowTest`, `OfflineAirplaneModeTest`) failed with:

```
AssertionError: app must NOT hold android.permission.INTERNET -- P-3 is offline-only
```

`NetworkAssertions.kt` was **stale P-3-era code**. P-6 added real resumable
HTTPS sync, the manifest now deliberately declares `INTERNET` and
`ACCESS_NETWORK_STATE`, and `app/build.gradle.kts`'s
`verifyExpectedNetworkPermissions` *requires* them with the message "P6
genuinely needs real networking". The two checks directly contradicted each
other; the instrumented one had simply not been run since P-6 (P10's device
gate ran a curated 22-test subset). Its own comment referenced
`verifyNoNetworkDependencies`, a Gradle task that no longer exists.

Fixed by asserting the invariant that is actually still worth holding after
P-6 — the app holds **exactly** the two permissions sync needs and **no**
location / Wi-Fi-state / connectivity-mutating / external-storage permission
— which mirrors the build-time allow-list at runtime. Offline *behaviour*
remains proven where it should be: by `OfflineAirplaneModeTest` actually
running the journey with the radios off.

This defect is unrelated to the cloud deployment (no Android source was
otherwise changed) but is reported here because it was found by this work.

## 8. Offline regression (Gate G)

The cloud changes must not alter the offline product. Re-verified after all
of them, with `infra/docker-compose.yml` and no cloud configuration at all:

| Check | Result |
|---|---|
| stack comes up healthy | PASS — api/dashboard/db healthy, worker running |
| `/health` | PASS — `{"status":"ok","database":"ok","storage":"ok"}` |
| **no `STORAGE_BACKEND`/`S3_*` variable in the container** | PASS — none present |
| active backend class | PASS — **`LocalDiskStorage`** |
| `probe()` via local disk | PASS — `True` |
| full 22-check P6/P7 smoke test | **PASS — all 22** |

`boto3` is present in the image but never imported in local mode (it is
imported lazily inside `S3Storage.__init__`), so no cloud dependency or
credential is introduced into the offline path.

## 9. Known limitations

* The deployed backend points at the Neon **`staging`** branch, not `main`.
  Switching is six environment variables (see `VERCEL_RAILWAY_NEON.md` §7).
* Neon Object Storage is currently a **beta** product. It behaved correctly
  throughout, but that is a dependency risk worth knowing before a demo.
* Railway's $5 is a **temporary trial** credit expiring 30 days from issue,
  not an ongoing free tier. See `VERCEL_RAILWAY_NEON.md` §6.
* Upload throughput measured *from this laptop* is slow (7.3 MiB took 75 s;
  a direct 12 MiB write to Neon took 288 s). That is this machine's uplink to
  Singapore, not the production path — Railway `asia-southeast1` → Neon
  `ap-southeast-1` is intra-region. Real Android field throughput is
  unmeasured.
* Dashboard and Android performance timings were not re-measured against the
  hosted deployment; `docs/perf.md`'s numbers remain local-stack figures.
