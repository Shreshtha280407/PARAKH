# P7 physical-device and live-dashboard run — 2026-10-14

**The requested functional checks passed after the fixes recorded below.** This was an
agent-driven run on the physical OnePlus 13R and visible Chrome windows. It is an engineering
gate record, not a human usability or occupational-competency validation. Phase closure and
commit/push remain with the repository owner.

Device: **OnePlus 13R, CPH2691, Android 16 / API 36**, connected over USB. `adb devices -l`
showed exactly one device in `device` state. The app reported version `0.6.0-p6`; the tested
APK was built from this P7 working tree. Branch:
`feature/p7-signed-report-reassessment`; HEAD:
`01dd65e10dc2ad2bfbebeddd2a0839fb4b72c3ea`. Existing uncommitted P7 work was retained.

## Results against the supplied steps

| Step | Result and evidence |
| --- | --- |
| 1 — physical device | PASS: one authorised CPH2691; SDK 36; no emulator |
| 2 — ports | PASS: unrelated TraceX occupied host port 8000. Used a temporary Compose override for API 18000 and dashboard 15173; TraceX was left running |
| 3 — real stack and seed | PASS after fixing repeated seeding with multiple existing assessments. Real PostgreSQL/evidence volumes retained; existing `.env` and signing key were not rewritten |
| 4 — phone-to-LAN health | PASS on recheck: both the phone and host returned `{"status":"ok","database":"ok","storage":"ok"}` from `http://100.129.166.179:18000/health`. The first probe timed out. Initial uploads used `adb reverse tcp:8000 tcp:18000`; a final in-app report-status poll used the LAN URL successfully |
| 5 — hardware instrumentation | PASS after correcting the command and one test setup: final run **11 tests, zero failures**, including both migrations, both required targeted-seal cases, repeated revision inheritance, and manual polling under Main-thread StrictMode |
| 6 — install/launch | PASS: `:app:installDebug` installed on the physical phone. Later fixes were installed with `adb install -r`, preserving this draft and its Keystore |
| 7 — fresh intake and two captures | PASS: fresh consent/registration, declaration and match; actual CameraX photos for T1 and T2. Match: `partial_match`, approximately 54.8% coverage |
| 8 — initial seal/sync | PASS: assessment **20**, revision **1**, two verified evidence items and a complete signed manifest |
| 9 — real browser | PASS: headed Chrome, seeded assessor login, actual assessment page and protected evidence gallery |
| 10 — scoring/profile | PASS: **17 T1 PCs and 11 T2 PCs** saved with practice remarks. The profile displayed **28 / 71**, NOS rows/flags and **INSUFFICIENT_EVIDENCE**, explicitly labelled decision support |
| 11 — T1 selection as written | PASS: requested only T1, with a reason and capture instructions. Request **5** opened revision **2** |
| 12 — update/banner/locks | PASS after fixing manual polling. T1 request unlocked T1 and locked T2. A subsequent T2 request unlocked T2 and locked T1; its actual reason/instructions were visible. Previously submitted locked evidence had no replace/remove controls |
| 13 — targeted recapture | PASS: completed T1-only recapture for the literal first request, then T2-only recapture for the later scenario. Each uploaded only the reopened task's new evidence |
| 14 — history/re-review | PASS for both cycles: v2 changes T1 and preserves T2; v3 changes T2 and preserves v2's T1. Only **11 CON/N0602 PCs** were flagged on the T2 cycle; T1 scores remained at revision 2 |
| 15 — wrong password | PASS: first completed sign-off attempt with a deliberately wrong password returned **401**, `incorrect password`; no report was produced by that attempt |
| 16 — re-review/override/sign | PASS: reopened PCs re-scored; zero remaining `needs_review` rows. Blank override with a correct password returned **422**. A real practice-specific explanation allowed final **NOT_YET_COMPETENT** against computed **INSUFFICIENT_EVIDENCE** |
| 17 — PDF/public page | PASS: PDF downloaded through the dashboard link; its embedded verification URL matched the opened page. A fresh unauthenticated browser context showed `SIGNED`, `valid: true`, and only permitted minimal fields |
| 18 — independent offline verifier | PASS: original PDF exited **0**, `signature OK`; a copy with exactly one byte flipped exited **1**, `TAMPERED` |
| 19 — report | This file, with durable evidence linked below |
| 20 — temporary override | Removed after verification; it is not part of the retained changes |

**Runbook correction:** selecting a task means reopening that task. The supplied step 11
selected T1, while steps 12–14 expected T2 to reopen and T1 to stay untouched. The user asked
to follow the T1 selection as written, so that was exercised first. A second, T2-only request
then covered the later expectations. Consequently the T2-only result is **v3**, following the
literal T1-only **v2**. Neither the product semantics nor the recorded revision numbers were
inverted to make the checklist appear to pass. The handoff document now selects T2 for its
T2-recapture example.

## Observed revisions and byte integrity

Assessment **20**, client UUID `d735c536-aa41-41b3-b928-0dcf52a90bed`, device worker
`KP-4AA622E3`. Server timestamps below are UTC.

| Revision | Submitted at | Reopened tasks | Upload sessions | New photo bytes |
| --- | --- | --- | --- | --- |
| v1 | 11:55:40.582984 | Initial T1 + T2 | 33 manifest, 34 T1, 35 T2 | T1: 1,356,335; T2: 1,352,281 |
| v2 | 12:14:30.581792 | T1 | 36 manifest, 37 T1 | 1,350,105 |
| v3 | 12:22:33.876161 | T2 | 38 manifest, 39 T2 | 3,146,340 |

The server-side verification independently re-read and hashed all four stored photos,
re-verified all three device-manifest signatures, checked complete sessions, exact byte
counts and contiguous chunk indexes, and checked each revision's snapshot. There are exactly
**4 evidence rows and 7 upload sessions** for this assessment, with one upload session per
photo. Every manifest has exactly the two active task items.

T1 inherited unchanged from v2 into v3:

```text
evidence_id: 6aa7408d-6725-40df-aa50-e77127a66b95
bytes:       1350105
sha256:      eb76e34d35600b37d225fe8ee3eeee2df42658d02dc4e7d9f0f99669a28bd6a2
```

T2's v3 replacement:

```text
evidence_id: f67f2b7b-fdb3-4304-b72d-d38ebe60c4ee
bytes:       3146340
sha256:      26e1c75d689fcef20fefa0698b7497cface307e34dffd9b1ac7ba405102b8dc1
```

The v1 and v2 signed snapshots remain intact. No superseded T1 item re-entered v3, and
session 39 is the only evidence upload for v3: T1 was inherited by its existing ID/hash.
Full evidence: [server-revision-integrity.json](evidence/P7-2026-10-14/server-revision-integrity.json).

## Failures found and corrected

| Finding | Correction and verification |
| --- | --- |
| Supplied Gradle command used unsupported `--tests` on `connectedDebugAndroidTest` | Used Android runner class filters in separate Gradle runs. Direct `adb am instrument` supported all three classes together for final checks and preserved the live assessment. Corrected the handoff commands |
| Missing-evidence instrumented case returned `NotReady` instead of reaching its intended guard | Test now first asserts `NotReady`, then reaches final review/attestation without adding evidence and still requires `NoEvidence`; revision and outbox must remain unchanged. No rejection guard was relaxed |
| Seeding crashed with `MultipleResultsFound` after a demo worker acquired multiple assessments | Changed the seed existence query to accept any existing assessment. Added a regression proving repeated seeding preserves all existing assessment identities/statuses |
| Consent and camera explanations still promised that nothing would be uploaded | Corrected English/Hindi consent, permission explanations and offline badge to describe private local capture followed by server sync after sealing. Verified new consent on-device and string parity |
| Targeted sealing overwrote the newly persisted hash and vault path using a pre-encryption row snapshot | Final SEALED write now retains both. Hardware regression reproduced a null hash and a subsequent-reassessment crash before the fix; passes afterward |
| Later targeted seals could include superseded evidence from earlier cycles | Inheritance now excludes `fromPreviousRevision` items. Added a two-reassessment regression with receipt-like deletion of prior vaults/outbox; final manifest must contain exactly the active items |
| Manual Check for updates crashed the app with `NetworkOnMainThreadException` | Blocking HTTP call now runs on `Dispatchers.IO`. Captured the real crash and added a hardware Main-thread StrictMode test for polling, locks, reason/instructions and repeated-poll attestation preservation |
| A later request could leave editing sealed when an older pending request was still cached | Detect new requests using revision number and reopened-task set. The new test failed with `FINAL_REVIEW_READY` before the fix and now verifies editing/attestation reset on a newer request, including repeated task codes |
| Reassessment notices left only a tiny task-list viewport; two badges squeezed titles into a narrow column | Summary and cards now share one scrolling LazyColumn; titles sit above badges. Re-ran both live recapture cycles with reachable, readable task cards |
| Untouched submitted evidence lacked its previous-submission label; locked tasks showed misleading discard-seal guidance | Locked sealed items show the previous-submission notice and have no preview/edit actions; removed that incorrect guidance for task locks. Real T1/T2 locked-state screenshots retained |
| Sign-off dropdown omitted the supported `INSUFFICIENT_EVIDENCE` outcome | Added the option; confirmed selection through the real browser before the wrong-password/override checks |
| Public-key export CLI imported only the checkout's `server.app`, failing inside Docker's flat `/code/app` layout | Supports both layouts. Four subprocess regression cases cover both layouts and hex/PEM output. Exported the real container's public key and used it for successful offline verification |

Before/after hardware logs and the original main-thread crash are in
[the evidence directory](evidence/P7-2026-10-14). The targeted seal and polling regressions
were demonstrated failing before their fixes; the final combined result is:

```text
SealOrchestratorInstrumentedTest: ........
AppDatabaseMigrationTest: ..
WorkerUpdatesRepositoryInstrumentedTest: .
Time: 9.309
OK (11 tests)
```

Commands used for the final hardware run:

```bash
adb install -r apps/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell am instrument -w \
  -e class in.kaushalpramaan.app.SealOrchestratorInstrumentedTest,in.kaushalpramaan.app.data.draft.AppDatabaseMigrationTest,in.kaushalpramaan.app.data.sync.WorkerUpdatesRepositoryInstrumentedTest \
  in.kaushalpramaan.app.test/androidx.test.runner.AndroidJUnitRunner
```

Relevant backend regressions: **7 queue/seed tests passed** and **4 public-key CLI tests
passed**. Android debug/test APK builds, dashboard Docker build, EN/HI parity and
`git diff --check` passed. This run did not repeat the entire previously recorded backend
suite or run hosted CI. The HTML reports for the initial and corrected Gradle runs are
preserved separately under the evidence directory.

## Signed report and independent verification

- Report ID: `ul1ep08zi8H0z4u3KNvOrg`, revision **3**.
- Signing key ID: `dev-key-2026-10-14`; the existing persisted key was retained.
- Signed at: `2026-10-14T12:25:27.513560Z`.
- PDF SHA-256: `1da4764eefbb4959d63ff97f96bc2957190809d3ae3bb4db27cdd998553ab3cb`.
- Final recommendation: `NOT_YET_COMPETENT`, with an explicit technical-practice override
  reason explaining the incidental photographs and absent demonstrations. Scores were
  `NOT_OBSERVABLE`; this was not represented as successful occupational performance.
- Final server state: `recommended`, zero pending score reviews. This lifecycle status
  records sign-off; the signed recommendation itself is `NOT_YET_COMPETENT`.
- Audit: 3 review starts, 56 score saves, 2 targeted requests, 2 resubmissions and one sign-off.

The fresh public browser context had no cookies. Its JSON contained only report ID, signed
status, validity, QP, recommendation, revision, digest, key ID and signing time; no worker
identity, declaration answers, evidence or PC remarks were exposed. The PDF's embedded
verification URL was found in its extracted text and opened successfully:

[Public verification page](http://localhost:15173/#/verify/ul1ep08zi8H0z4u3KNvOrg).

Downloaded artifacts:

- [Signed PDF](evidence/P7-2026-10-14/assessment-20.pdf)
- [Detached receipt](evidence/P7-2026-10-14/assessment-20.pdf.receipt.json)
- [Trusted public key](evidence/P7-2026-10-14/report-public-key.pem)
- [Offline verifier results](evidence/P7-2026-10-14/offline-verification.json)

```bash
python tools/verify_report.py /tmp/parakh-p7-20261014/assessment-20.pdf \
  --pubkey /tmp/parakh-p7-20261014/report-public-key.pem \
  --receipt /tmp/parakh-p7-20261014/assessment-20.pdf.receipt.json
# exit 0: signature OK; PDF hash matches
```

Flipped exactly one byte at offset **15,769** in a copy. The same verifier and receipt
returned exit **1**, `TAMPERED`; the signed original remained unchanged. Its two-page PDF
also rendered successfully for visual inspection.

## Final state and cleanup

The phone's sync URL was set to `http://100.129.166.179:18000`. A final Check for updates
completed over LAN and displayed **“Your signed report is ready.”** Airplane mode was OFF.
The USB reverse tunnel was retained as a fallback. API, PostgreSQL and dashboard health
checks passed, and the worker remained running. Dashboard: `http://localhost:15173`.

Removed the task-created `infra/docker-compose.override.yml` as requested. The running
containers retain their tested port mappings. No database/evidence volume was removed,
no unrelated service was stopped, and no commit, push, stash or reset was performed.

Additional temporary screenshots/XML/JSON and the tampered test copy remain under
`/tmp/parakh-p7-20261014/`. Durable gate evidence excludes credentials, private keys,
worker capability tokens and raw camera photographs. The existing uncommitted P7 work
and the corrections above remain available for owner review.
