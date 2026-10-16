# IC-2 / Q4 / P8 integration report — 2026-10-15 / 16

The functional Android → signed manifest → backend → dashboard implementation now has
physical **CameraX/product-screen, OS WorkManager process recovery, interrupted sync and
P7 targeted reassessment** evidence on the OnePlus. See the
[2026-10-16 continuation report](IC2_Q4_P8_20261016.md) and
[redacted run records](IC2_Q4_P8_20261016/verification.json).

**Q4 FUNCTIONAL INTEGRATION: PASS. P8 FUNCTIONAL INTEGRATION: PASS.**
P8 C/D/E passed for the executed product workflow; A/B remain NOT VERIFIED.
**Overall handoff: PARTIALLY COMPLETE. Complete owner acceptance remains INCOMPLETE**
because the independent 10-bad/10-good capture exits and three-phone field/device-tier
validation are unavailable. The owner confirmed only the OnePlus is available.
Original IC-2 acceptance is **FAIL / NOT ACCEPTED** because Q3 remains below 90%.
No commit/push, algorithm/threshold change or acceptance weakening occurred.

The architecture and October 15 run details below are retained. Dated physical limitations
in that earlier record are superseded only where the October 16 report supplies new evidence.

## Source of truth and initial audit

The initial working tree was clean on `main`, HEAD
`0f0e1f64f033851668e0b98ce2bb0853eefc86fd`; the historical baseline was inspected, never
reset. Local master-plan PDF pages 23/26, Q2/Q3 amendment/acceptance/recovery records,
P4/P5/P6/P7 gates, Android Room/migrations/public analyzer APIs, backend schemas/OpenAPI,
manifest verification/auth and dashboard evidence/history/player code were read first.
The owner's instruction authorises functional integration despite unmet original IC-2
accuracy/performance gates. Semantic task-target framing remains explicitly excluded.

Initial map: CameraX `CaptureScreen` → `AppViewModel` → promoted private evidence in
`EvidenceRepository`; Room v5/SQLCipher owns drafts, P5 state/outbox and P6/P7 history;
`SealOrchestrator` selects final bytes, signs the canonical manifest and encrypts the
package; `SyncRepository` sends manifest then resumable evidence; the server verifies and
binds evidence before exposing it through authenticated assessment APIs; the existing
React gallery owns the native player. These are the implemented integration points.

## Implemented architecture and lifecycle

```mermaid
flowchart LR
  C[CameraX capture finalisation] --> R[EvidenceRepository]
  R --> A[Assistance coordinator]
  A --> D[(Room v6 / SQLCipher)]
  A --> W[Unique WorkManager job]
  W --> Q[Existing offline Q2 / Q3 APIs]
  Q --> D
  D --> U[Evidence and final previews]
  R --> O[P5 optimisation / trim]
  O --> A
  O --> S[Freeze exact-byte assistance snapshot]
  D --> S
  S --> V[ECDSA signed manifest + encrypted vault]
  V --> P[P6 resumable sync]
  P --> B[Verify signature / contract / media binding]
  B --> E[(EvidenceItem assistance + existing quality status)]
  E --> G[Authenticated existing assessor gallery]
  G --> T[Native player / interval seek]
```

Both production module dependencies are real, with the existing CPU MediaPipe model bundled
once, uncompressed, and no runtime download. Analysis does not rewrite media. The decoder,
quality thresholds, sample policy (Q2 1 s anchors plus 125 ms partners; Q3 1 fps/640 px),
YUV optimisations and isolated-gap hands policy are unchanged.

Production manifest overrides remove MediaPipe's transitive DataTransport/CCT backend
discovery and upload service/receiver. Hardware logs exposed its statistics scheduler
once the libraries consumed the app's legitimate P6 INTERNET permission. The published
library bytecode confirms that statistics use DataTransport; no inference algorithm is
patched. Debug/release merged-manifest checks and on-phone package inspection require
those telemetry components to be absent. P6 networking remains available.

Room adds one assistance row per evidence item with assessment/task/revision, generation,
input path/SHA-256/duration, state/stage, compact typed result, frozen signed snapshot and
stable error. No landmarks, identity data or per-frame metric dumps are retained. Photos
schedule after successful promotion; videos use background work. Unique work and a shared
native semaphore prevent unrestricted decoder/model concurrency. Recovery checks actual
WorkManager generations and repairs orphaned queued/running work. Retry/cancellation is
safe while editable. Deleted/replaced evidence cannot be resurrected by delayed work.
Scheduling/cancellation serialize generation changes with WorkManager operation order,
including simultaneous retries across coordinator instances. The worker retains its normal
two-argument constructor; a WorkerFactory can inject an isolated database for physical
tests without changing its production execution body.

The worker verifies input hashes before and after inference and rechecks current generation,
revision, path and editability transactionally before applying results. Room is the durable
UI source across Activity recreation. Queued/running is never a bad capture; failed and
unavailable have no fabricated quality verdict. Partial results retain explicit coverage.
Warnings explain dark, overexposed, blur and motion heuristics; hands advice discloses
possible missed detections and never implies competence, PPE, tools or identity verification.
Retake/delete controls and existing size/integrity/attestation gates remain in their product
screens. Advice cannot disable valid submission.

Optimisation reanalyses changed bytes/duration. Equal SHA-256 and duration prove safe reuse,
including a changed path while equivalent-byte work runs. Missing capture video metadata is
recovered from P5's validated final container; analysis failure is not a submission limit.
P5 transitions to `SEAL_IN_PROGRESS` before reading snapshots, without awaiting inference.
Completed results or honest pending/unavailable state are copied into schema-2 canonical
signed bytes. Late workers cannot update sealed observations. Historical P7 evidence keeps
its exact original snapshot/revision; new recaptures receive a new result. Signed reports
and competency/scoring algorithms do not consume assistance.

## Contract, persistence and security

`contracts/flags.schema.json` version 1 is generated from strict Pydantic models and mirrored
by Kotlin serializable types. Shared synthetic fixtures round-trip in Python/JSON Schema
and Kotlin. Status, source, condition, severity and error meanings are bounded; intervals
are half-open source-relative integer milliseconds. Nonfinite/negative/out-of-range values,
unknown fields/versions, invalid provenance, duplicate/oversized flags and evidence binding
mismatches are rejected. Flags cannot exceed signed duration. The player also checks actual
playable duration. It explains duration mismatches, intersects visible ranges with playable
footage without changing signed timestamps, and disables starts outside the playable range.

Manifest schema 1 and pre-version legacy envelopes remain valid without assistance; schema
2 includes assistance inside the existing exact ECDSA signature. The server never re-signs
client evidence. Existing TOFU signing identity, canonical-byte verification, file hashes,
size/task binding, upload idempotency, resumability and revision relationships are retained.
Inherited observations must equal already verified server snapshots. No unsigned metadata
update API or backend inference service exists.

Room `MIGRATION_5_6` is additive, with an evidence foreign key/cascade. Exported schema 6 is
included. Tests migrate populated schema 5 through real Room and real on-phone SQLCipher,
checking assessments, sealed evidence/history, reassessment, outbox progress and receipts.
Alembic `b89e72c4d010` (parent `af3b2cddce3e`) adds one nullable JSON column. A populated
prior-schema migration test compares preserved rows; legacy evidence remains null/not_run.
`EvidenceItem.quality_check_status` describes the signed snapshot using existing lowercase
status conventions. Authenticated existing assessment/evidence endpoints expose typed data;
no new competing state machine or public assistance endpoint was introduced.

Canonical metadata is bounded to 1,400,000 bytes inside the unchanged 2 MiB signed envelope
ceiling. New excessive diagnostics become honest UNAVAILABLE/PAYLOAD_LIMIT before signing;
inherited snapshots and media budgets/hashes are unchanged. Individual assistance is limited
to 256 flags/65,536 bytes. In the synthetic five-item API fixture, canonical assistance added
3,613 bytes and the full signed envelope was 7,022 bytes; this is measured fixture overhead,
not an upper bound for every assessment.

Existing assessment authorization and protected player media remain in use. Negative tests
cover unauthenticated and other-assessment access, signature/flag tampering and wrong
identity/revision. Browser checks observe zero scoring/outcome/reassessment mutations when
viewing flags. Human actions still determine every PC score, reassessment and signed outcome.

## Important modified files

Paths below are repository-relative; directories group closely related new files.

| Files | Purpose |
|---|---|
| `apps/android/app/build.gradle.kts` | Production dependencies, uncompressed model, source stamp/test assets; fix KSP/lint ordering |
| `apps/android/app/src/main/AndroidManifest.xml` | Remove transitive statistics upload components while preserving P6 networking |
| `apps/android/app/src/main/kotlin/in/kaushalpramaan/app/data/assistance/` | Coordinator, durable row/DAO, worker, native adapter and stale-result guard |
| `.../data/draft/AppDatabase.kt`, `app/schemas/.../6.json` | Additive Room migration and exported schema |
| `.../data/draft/EvidenceRepository.kt` | Post-promotion scheduling, delete/replace cancellation and recovery |
| `.../data/AppViewModel.kt`, `AppState.kt` | Observe results, wire real repositories, retry/cancel and chosen media |
| `.../data/seal/SealOrchestrator.kt` | Optimisation invalidation, container metadata recovery, immutable snapshots/inheritance |
| `.../ui/components/AssistanceCard.kt`, `.../ui/screens/EvidencePreviewScreen.kt`, `PreviewScreen.kt` | Existing worker previews, compact review, advisory guidance and actions |
| `apps/android/app/src/main/res/values*/strings.xml` | Matching EN/HI guidance |
| `apps/android/core/seal/.../AssistanceSnapshot.kt`, `SealManifest.kt` | Strict compact wire types, signed optional metadata, legacy omission and size fallback |
| `apps/android/app/src/test/.../data/assistance/`, `core/seal/src/test/.../AssistanceContractTest.kt` | Real Room/WorkManager lifecycle, migration and shared-contract tests |
| `apps/android/app/src/androidTest/.../Assistance*InstrumentedTest.kt` | Real native inference, encrypted migration, Compose advice, native HTTP upload/reassessment |
| `.../data/sync/SyncRepositoryInstrumentedTest.kt` | Preserve pre-existing matching JPEGs while detecting new/changed plaintext copies |
| `server/app/assistance.py`, `manifest_verify.py` | Strict version-aware signed validation and malformed input handling |
| `server/app/models.py`, `schemas.py`, `routers/uploads.py`, `routers/assessments.py` | Verified persistence, status and authorized response propagation |
| `server/alembic/versions/b89e72c4d010_p8_signed_assistance.py` | Additive nullable assistance column |
| `server/tests/test_assistance.py`, `server/tests/test_reports.py` | Contracts, signed HTTP/migrations/security; deterministic real lock-contention regression |
| `contracts/flags.schema.json`, `contracts/fixtures/`, `contracts/openapi.json` | Versioned schema, shared synthetic fixtures and refreshed API |
| `apps/dashboard/src/components/EvidenceAssistance.tsx`, `pages/AssessmentDetailPage.tsx`, `types.ts`, `index.css` | Existing-gallery metadata, accessible lanes/seek, actual duration and responsive layout |
| `apps/dashboard/e2e/p8*.mjs`, `package*.json` | Persisted synthetic and native-device browser harnesses; pinned Playwright |
| `tools/export_flags_schema.py`, `integration_source.py`, `p8_e2e.py`, `p8_acceptance.py` | Freshness/source identity, real HTTP lifecycle and honest field-exit scoring |
| `infra/docker-compose.p8-test.yml`, `docker-compose.p8-local.yml` | Isolated verification stack; current-source cached-image fallback |
| `.github/workflows/ci.yml` | Contract freshness, production asset verification and persisted browser checks |
| `docs/gates/{IC2,Q4,P8,Q4_device_protocol}.md`, `docs/evidence_quality_result.md`, `docs/assistance_modules.md` | Actual contract, architecture, acceptance boundaries and reproduction |

## October 15 executed verification

This table records the earlier broad run. See the [October 16 continuation](IC2_Q4_P8_20261016.md)
for fresh production builds, backend subset, CameraX/OS recovery and seven real-camera browser checks.

Durable redacted scalar results and selected passing transcripts are in
[`IC2_Q4_P8/`](IC2_Q4_P8/). No APK/build output, raw recording, connectivity dump, worker
credential or private-media path is included. Local detailed logs are `/tmp/parakh-p8-*`.

| Check | Actual result / boundary |
|---|---|
| Android unit tests | 190 passed, zero failures/errors/skips: app88, seal24, media21, budget12, mapping13, quality23, hands9 |
| Android debug/release + instrumentation compilation | PASS; latest `:app:check` includes lint and release policy checks. Baseline release minification/resource shrinking remain disabled; the separate enabled R8/shrinker QA build now passes build, native initialization and encrypted reopen, with actual recovered native inference on the preceding R8 artifact |
| All-module Android lint/regressions | PASS in earlier broad run; final changed app checks rerun |
| Model/profile APK verification | PASS debug/release, correct bundled source/model assets, unchanged sampling/config |
| Backend full suite, real isolated PostgreSQL | 278 passed in 419.34 s; one upstream Starlette httpx deprecation warning |
| Assistance Python contract/HTTP/migration subset | 43 passed; included in full 278 |
| Assistance intake/protocol/evaluation Python | 21 passed; golden quality vectors, frozen historical replays and matcher/pack checks pass |
| OpenAPI + flags schema freshness | PASS |
| Dashboard typecheck/build | PASS |
| Dashboard lint | PASS with two existing set-state-in-effect warnings in QueuePage / VerifyReportPage |
| Signed API E2E | PASS real HTTP/PostgreSQL: chunk interruption/resume/idempotency, warning/pending/unavailable submission, revisions/inherited snapshot isolation |
| Existing direct-upload P2.2/P7 smoke | PASS, including human scoring/signing, report verification and token rotation/revoke |
| Existing signed P6/P7 smoke | PASS, including reassessment, score preservation and tampered-report rejection |
| Browser boundary harness | 19 checks PASS using actual persisted signed synthetic snapshots and native H.264 playback |
| Native-device browser harness | PASS actual Android-generated flags after real signing/upload and targeted reassessment; see device run evidence |
| Physical-device instrumentation | 23 passed, zero failures/ignored, 22.084 s final run; includes real WorkManager/native execution; no emulator substituted |
| Hosted GitHub Actions | NOT RUN: no commit/push; workflow YAML parses locally |
| New field capture / three-phone exits | NOT VERIFIED |

The 19 browser checks cover video start, 4,999 ms near end, simultaneous/overlapping flags,
click/keyboard/touch seek, revisions, pending/unavailable/legacy, 360 px resize/44 px targets,
unauthenticated denial, media failure/missing duration and a signed 6 s versus playable 5 s
mismatch. Every marker uses milliseconds and the existing player. No local-only mocked API
was used for these checks.

Failures found and fixed: combined lint/KSP task ordering caused a build race (dependencies
made explicit); a pre-existing timing-based P7 concurrency test was load-sensitive (now
observes the actual PostgreSQL Lock wait before holding the lock, preserving its original
rejection/duration assertions); P6's JPEG prefix scan matched older legitimate drafts (now
compares pre-existing whole-file hashes); test fixture filename and browser test login-cookie
handling were corrected. Failed checks were rerun, not disabled. The first Docker image
build succeeded; a later fresh rebuild hit registry DNS failure outside the sandbox as well.
Current-source tests used cached images with read-only source/dist mounts. No final clean
registry rebuild or hosted-CI success is claimed.

## October 15 real device and preservation record

Device: owner-confirmed OnePlus 13R CPH2691, Android 16/API36, serial `d34cebae`.
Final run: `p8-native-38926584918743`, native upload assessment 16, old/current video IDs
33/34, photo 32 in the isolated test stack. Base HEAD is above; the uncommitted source
stamp is `a5727df00cc6124b78b81cb50495312a9faf0a8dd5531ab2af76ab9f781b5537`.
The APK source stamp and hashes are retained in [verification.json](IC2_Q4_P8/verification.json).
Owner explicitly confirmed updating both named packages using `adb install -r`. Neither
package was uninstalled or cleared. Only isolated databases and generated synthetic evidence
were used; the legacy `ClearP4DraftBeforeTest` UI classes were deliberately not run on this
personal device. Scope is documented in [the device protocol](../gates/Q4_device_protocol.md).

The offline native tests assert no network with INTERNET capability, rather than trusting an
airplane-mode toggle. Native inference/signing/sealing and the encrypted populated v5→v6
migration ran on hardware. USB reverse provided a local-only route for production P6 sync,
authenticated retrieval and an explicit assessor-driven T2 reassessment. Frozen results were
compared as typed snapshots after server storage; old T2 and inherited T1 stayed unchanged.
Native browser checks then played those actual uploaded videos and sought their real flags.
These inputs are generated JPEGs and bundled two-second test videos, not new field captures.
The production coordinator also ran real post-finalisation WorkManager photo/video jobs
on the phone, using an in-memory work database and an injected isolated SQLCipher database.
The actual worker body/native engines completed, preserved media hashes and reused results
without duplicate inference. Production `kp_drafts.db` and existing WorkManager jobs were
not touched. A true killed-process recovery run remains NOT VERIFIED.

A local pre/post SHA-256 inventory covered 65 pre-existing database/file entries: no deletion;
main `kp_drafts.db` and WAL unchanged; all pre-existing evidence unchanged. The only changed
entry was Android's `files/profileInstalled` APK-install marker. Full path/hash inventories
stay outside Git. Original connectivity (airplane0/Wi-Fi0/mobile-data1) was restored after
runs. App data, original recordings, assessment/report history and root `.env` were preserved.

Synthetic short-clip timing is recorded per generated evidence in `native-run.json`.
Final run: dark photo 69 ms; two-second videos 866 ms and 750 ms, measured inside the
native runner including hash/state work. These are not isolated library inference timings.
Do not extrapolate it into representative video-minute or required-tier performance.
An intermediate combined run observed a 189,353 ms two-second video analysis, versus
1,146/1,037 ms clips in an earlier isolated native run. A diagnostic SIGQUIT was requested
before that run completed; its timing is not an uncontaminated benchmark and the cause
was not established. This outlier is retained as a reliability limitation, not omitted
in favour of the faster measurements. That combined run also correctly failed two offline
assertions because network teardown had not finished. The harness now waits up to 30 s
for actual disconnection and still fails if an INTERNET-capable network remains.
Integration overhead, observed peak memory, complete worker UI responsiveness and process
restart recovery on physical hardware are NOT VERIFIED. No fast estimate is shown in UI.

## Original IC-2 acceptance and remaining work

| Gate | Required | Evidence | Verdict |
|---|---|---|---|
| Q2 precision | ≥85% | Inherited latest proxy 92.5% | PASS on proxy; independent acceptance NOT VERIFIED |
| Q2 recall | ≥80% | Inherited latest proxy 92.5% | PASS on proxy; independent acceptance NOT VERIFIED |
| Q3 agreement | ≥90% | Inherited gap-filled 75.8% | FAIL |
| Entry-phone video runtime | ≤5 s/video-minute | Inherited 21.6 s/min OnePlus flagship; no entry phone | NOT VERIFIED on required tier |
| Mid-phone hands inference | ≤60 ms/frame | No required-tier device run | NOT VERIFIED |
| Android production integration | Functional | October 16 real CameraX, worker navigation, OS analysis/upload recovery, signing, sync and browser | PASS on available OnePlus |
| Signed flag persistence | Functional | Real native ECDSA, P6 upload and exact stored snapshot comparisons | PASS |
| Dashboard markers | Functional | Persisted synthetic boundaries + actual native flags seek | PASS |
| P8 exit scenarios | Original A/B/C plus D/E | C/D/E passed; independent A/B captures unavailable | NOT VERIFIED as combined exit |
| Independent field validation | Separate representative evidence | No new independent holdout / three-phone run | NOT VERIFIED |

Original IC-2 is not accepted. No model/threshold tuning or sampling reduction was attempted
in this integration phase. Latest figures above remain historical recovery evidence, not
measurements regenerated by this work. Preserve the frozen historical replay profiles.

The CameraX/worker-screen lifecycle/offline-to-online run is now recorded in the continuation.
Finish representative field collection with the [device protocol](../gates/Q4_device_protocol.md). Collect
entry/mid measurements and an independent holdout before reconsidering original IC-2.
Functional API integration and formal field/accuracy acceptance are distinct. The code is
reviewable; this report does not describe the combined request as 100% complete.

## Reproduction commands

From the repository root; use disposable test databases only. Backend tests intentionally
recreate their target schema and must never point at an existing development/production DB.
Commands below use the separate test container from this session:

```sh
cd apps/android
./gradlew :app:check :app:assembleDebug :app:assembleRelease :app:assembleDebugAndroidTest \
  :core:budget:test :core:mapping:test :core:seal:testDebugUnitTest :media:testDebugUnitTest \
  :assist-quality:testDebugUnitTest :assist-hands:testDebugUnitTest lint --console=plain
cd ../..
python3 tools/verify_assistance_assets.py --require-calibrated \
  --apk apps/android/app/build/outputs/apk/debug/app-debug.apk \
  --apk apps/android/app/build/outputs/apk/release/app-release-unsigned.apk
python3 tools/check_android_string_parity.py
TEST_DATABASE_URL=postgresql+psycopg://parakh_p8:p8_ephemeral_test_only@127.0.0.1:55438/parakh_p8_tests \
REPORT_SIGNING_PRIVATE_KEY=c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1 \
server/.venv/bin/python -m pytest server/tests -q
REPORT_SIGNING_PRIVATE_KEY=c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1 \
server/.venv/bin/python tools/export_openapi.py --check
server/.venv/bin/python tools/export_flags_schema.py --check
python3 -m unittest discover -s ml/assistance -v
python3 ml/quality/generate_vectors.py --check
python3 ml/mapping/test_matcher.py
python3 ml/mapping/test_golden_vectors.py
python3 tools/pack_validate.py packs/ae-con-q0602
python3 tools/audit_qp_traceability.py packs/ae-con-q0602
cd apps/dashboard
npm ci
VITE_API_BASE_URL=http://127.0.0.1:18008 npm run build
npm run lint
cd ../..
docker compose -f infra/docker-compose.p8-test.yml up -d --build
docker compose -f infra/docker-compose.p8-test.yml exec -T api python -m app.seed
server/.venv/bin/python tools/p8_e2e.py --base-url http://127.0.0.1:18008 \
  --assessor-email p8-assessor@parakh.test --assessor-password p8-isolated-test-only --out /tmp/p8-api.json
server/.venv/bin/python tools/docker_e2e_smoke.py --base-url http://127.0.0.1:18008 \
  --assessor-email p8-assessor@parakh.test --assessor-password p8-isolated-test-only
server/.venv/bin/python tools/docker_e2e_smoke_p6.py --base-url http://127.0.0.1:18008 \
  --assessor-email p8-assessor@parakh.test --assessor-password p8-isolated-test-only
cd apps/dashboard
npx playwright install --with-deps chrome
P8_FIXTURE=/tmp/p8-api.json npm run test:p8
cd ../..
server/.venv/bin/python tools/p8_acceptance.py --out /tmp/p8-field.json
```

The test PostgreSQL container was started without host data mounts:
`docker run --name parakh-p8-tests-postgres-20261015 -e POSTGRES_USER=parakh_p8 -e POSTGRES_PASSWORD=p8_ephemeral_test_only -e POSTGRES_DB=parakh_p8_tests -p 127.0.0.1:55438:5432 -d postgres:16-alpine`.
It already exists locally; do not recreate or attach tests to the primary DB.
Physical installation/offline/native upload/browser commands and field JSONL format are in
[Q4_device_protocol.md](../gates/Q4_device_protocol.md). Historical replay commands stay in
CI using `quality-proxy-v2.json` and `hands-proxy-v1-model.json`, not current assets.

Functional product-path checks: **Q4 PASS, P8 PASS** for orchestration, worker screens,
signed propagation, process recovery, sync, reassessment and review on the available phone.
The overall request is **PARTIALLY COMPLETE** because independent field exits and required
hardware are unavailable. **P8 EXIT TESTS: NOT VERIFIED; IC-2 ORIGINAL ACCEPTANCE: FAIL.**
