# P7 physical-device + live-dashboard handoff — Codex Sol 6.1 xhigh

The 2026-10-14 physical run and corrections are recorded in
[P7_physical_device_2026-10-14.md](P7_physical_device_2026-10-14.md). The historical prompt
below describes its starting state; its Gradle filtering and task-selection examples have
been corrected from observed failures. Owner review of the completed run remains pending.

This document exists so the prompt below can be copy-pasted in full to a
separate Codex Sol 6.1 (xhigh reasoning) session with **no other
context** — it must be fully self-contained. Do not summarize or
paraphrase it before sending; send it verbatim.

---

## PROMPT (send everything between the two `=====` lines, verbatim)

=====

You are Codex Sol 6.1, running at xhigh reasoning effort. You are
testing **P7** of the PARAKH / KaushalPramaan project on **real
hardware** — a physical OnePlus 13R Android phone and a real backend —
because the automated test suites (225 backend pytest, Android unit/
lint/build, dashboard build, two full Docker Compose end-to-end smoke
scripts) have already passed and cannot, by themselves, prove the
on-device instrumented behavior or a human-driven dashboard review
actually work. You have no access to the conversation that produced
this code; everything you need is below or in the repo itself.

### 0. Ground truth — repo, branch, commit

- Repo root: `/home/Shreshtha/documents/PARAKH` (work **in place**, in
  this exact checkout — do not clone to a new location).
- Branch: `feature/p7-signed-report-reassessment`.
- Base commit this branch was cut from: `01dd65e10dc2ad2bfbebeddd2a0839fb4b72c3ea`
  (merge of PR #7, `feature/p6-resumable-sync-review`, on `main`).
- **The P7 work itself is intentionally uncommitted** — it exists only
  as working-tree changes on top of that commit (run `git status` to
  see ~59 changed/new files; run `git diff 01dd65e10dc2ad2bfbebeddd2a0839fb4b72c3ea --stat`
  for the full list). This is deliberate: the repo owner commits and
  pushes manually, only after this gate passes. **Do not commit, amend,
  stash, `git checkout`/`restore`/`reset`/`clean` anything, and do not
  push.** Treat the working tree as the thing under test, exactly as it
  sits.
- Read `docs/gates/P7.md` now — it is the living design/verification
  record for everything you are about to re-test (reuse rationale,
  pinned-pack-data basis for the computed outcome, the task-specific
  reassessment protocol, the report-signing redesign, and a disclosed
  incident from this session's own verification work — read it so
  you understand what's already been proven and why).

### 1. What you are proving that automated tests could not

P7 added, on top of the already-complete P1-P6 work:
1. A computed NOS-wise competency outcome (pinned-pack thresholds +
   critical-PC rule) shown to the assessor as decision support only.
2. Task-specific (not whole-assessment) reassessment: the assessor
   reopens specific task(s) with a mandatory reason; the worker's app
   unlocks *only* those tasks; unchanged tasks' evidence is reused by
   reference (never re-uploaded — the original vault file is already
   deleted from the phone by the time a reassessment can arrive, so
   this is load-bearing, not an optimization); the server versions the
   resubmission (v1 immutable, v2 new).
3. A periodic Android background poll for pending reassessment/report
   status (`WorkerUpdatesWorker`, 15-minute `PeriodicWork` — the
   Android platform floor for periodic work, so don't expect faster
   than that without a manual "check for updates" tap).
4. Password-confirmed sign-off (re-verified server-side against the
   *authenticated* assessor, not a frontend check) producing one
   immutable, Ed25519-signed PDF, stored as actual bytes (never
   re-rendered on redownload).
5. Public, unauthenticated report verification: `GET /verify/{report_id}`
   and a dashboard page at `#/verify/:reportId` (what a signed PDF's own
   QR code points at), plus an offline `tools/verify_report.py` that
   independently re-hashes a PDF and checks its Ed25519 signature
   against a trusted public key with no network call at all.

Two specific instrumented tests exist for #2 but have **never run
against real hardware** — only built successfully
(`./gradlew :app:assembleDebugAndroidTest`). They are the actual gate:
`apps/android/app/src/androidTest/kotlin/in/kaushalpramaan/app/SealOrchestratorInstrumentedTest.kt`:
  - `targeted_revision_reuses_unchanged_tasks_by_reference_and_only_vault_encrypts_the_reopened_task`
  - `targeted_revision_fails_closed_when_the_reopened_task_has_no_new_evidence`

And `apps/android/app/src/androidTest/kotlin/in/kaushalpramaan/app/data/draft/AppDatabaseMigrationTest.kt`:
  - `migrate_4_to_5_adds_reassessment_columns_with_safe_defaults_and_preserves_existing_rows`

### 2. Device

A physical **OnePlus 13R** (model `CPH2691`, Android 16, SDK 36) was
used for every prior physical-device gate (P4, P5, P6) and should be
used again for consistency — but any physical Android device meeting
`compileSdk`/`minSdk` in `apps/android/app/build.gradle.kts` is
acceptable if that exact unit isn't available; note the substitution in
your final report if so. **An emulator is not acceptable** for this
gate — Android Keystore, CameraX, and MediaCodec behavior on an emulator
does not reliably represent real hardware, which is exactly why this
gate exists.

```
adb devices                              # must show exactly one device, status "device"
adb shell getprop ro.product.model       # expect CPH2691 (or note the substitute)
adb shell getprop ro.build.version.sdk   # expect 36 (or note the substitute)
```

Connect by USB (preferred, avoids Wi-Fi flakiness mid-test) or
`adb connect <phone-ip>:5555` if you've already paired wireless debugging.

### 3. One-time environment setup

Follow `apps/android/README.md`'s "One-time environment setup" section
verbatim (JDK on `PATH`, Gradle wrapper, Android SDK via `cmdline-tools`,
`local.properties` pointing `sdk.dir` at it) if this environment doesn't
already have it configured — check `apps/android/local.properties`
first; it may already exist and be correct.

### 4. Bring up a real backend this phone can reach

This machine may have **other, unrelated processes already bound to
ports 8000 and/or 5173** (confirmed true during this work's own earlier
verification — check with `ss -ltnp | grep -E '8000|5173'` before
assuming they're free). If either is occupied:

```
# Create a LOCAL-ONLY, NEVER-COMMITTED override (same pattern this
# session used for its own verification -- delete it again when done):
cat > infra/docker-compose.override.yml <<'EOF'
services:
  api:
    ports: !override
      - "18000:8000"
  dashboard:
    ports: !override
      - "15173:80"
EOF
```

Then, with a real `.env` at the repo root (copy `.env.example` if one
doesn't already exist — **do not overwrite an existing `.env` without
reading it first**, see the incident in `docs/gates/P7.md` §8 for
exactly why that matters):

```
docker compose --env-file .env -f infra/docker-compose.yml \
  [-f infra/docker-compose.override.yml] up -d --build
docker compose -f infra/docker-compose.yml ps        # api, db, dashboard -> healthy
docker compose -f infra/docker-compose.yml exec api python -m app.seed
```

Find this machine's real LAN IP (`ip addr` / `ifconfig`) — the phone
needs `http://<lan-ip>:<api-port>`, not `localhost`. Confirm reachability
from the phone itself before trusting the app:

```
adb shell curl -s http://<lan-ip>:<api-port>/health   # or open it in the phone's browser
```

If port 8000/5173 were free and you didn't need the override, delete
this step's instructions accordingly (don't create a file you don't
need). Either way, **delete `infra/docker-compose.override.yml` again
once you're done** — it must never be committed.

### 5. Run the instrumented tests on the physical device first

Before any manual exploration, run the actual gate tests:

```
cd apps/android
./gradlew :app:connectedDebugAndroidTest \
  -Pandroid.testInstrumentationRunnerArguments.class=in.kaushalpramaan.app.SealOrchestratorInstrumentedTest \
  --console=plain
./gradlew :app:connectedDebugAndroidTest \
  -Pandroid.testInstrumentationRunnerArguments.class=in.kaushalpramaan.app.data.draft.AppDatabaseMigrationTest \
  --console=plain
```

Expected: all tests pass, including the three named in section 1.
Capture the full console output and the HTML test report
(`apps/android/app/build/reports/androidTests/connected/...`) as
evidence. If anything fails, do not patch around it blindly — read the
failure, determine whether it's a real P7 defect (most likely) or an
environment issue (e.g. permission grant quirks some OEM builds have —
see `apps/android/README.md`'s note on `GrantPermissionsViaShell`), fix
real defects, and re-run until green or until you've exhausted
reasonable attempts (document what you tried either way).

### 6. Full worker journey on the device, driving the real UI

Install and launch:

```
./gradlew :app:installDebug
adb shell am start -n in.kaushalpramaan.app/.MainActivity   # or just launch it on the phone
```

1. Fresh registration + declaration + match (regression — should behave
   exactly as P3-P6 already proved; if it doesn't, that's a real
   regression, not an out-of-scope finding).
2. Capture real evidence (camera photo/video, not mock) for **at least
   two tasks**, e.g. T1 and T2.
3. Point the in-app sync target at the backend from section 4 (debug
   build's `P6_TEST_ONLY sync server URL` field on the sealed-assessment
   screen — see `infra/README.md`'s "Reaching this stack from a physical
   Android device" section) and let it sync. Confirm on the dashboard
   (section 7 below) that the submission arrived.

### 7. Live dashboard: assessor review + targeted reassessment

Open the dashboard at `http://localhost:<dashboard-port>` in a real
browser (not Playwright-headless-only — actually look at it), log in
with the seeded assessor credentials (`DEV_ASSESSOR_EMAIL`/
`DEV_ASSESSOR_PASSWORD` from your `.env`), find the assessment you just
synced, and:

1. Score the performance criteria for both tasks.
2. Open the **competency profile** panel — confirm it shows a computed
   outcome (not a blank/error state) with NOS-wise meets-threshold/
   critical-violation flags, explicitly labelled decision-support only.
3. Open **Targeted reassessment**, select **only T2** (or whichever task
   you want to reopen; the unselected tasks stay untouched), write a real reason and capture
   instructions, submit it. Confirm the dialog closes successfully and
   the assessment's status/revision history panel reflects the new
   pending request.

### 8. Back on the device: the reassessment actually arrives and unlocks only the right task

Either wait for the 15-minute periodic poll or trigger the in-app
"Check for updates" action if the UI exposes one (`TaskListScreen.kt`'s
summary card). Confirm:
- A banner shows the reassessment reason/instructions.
- The **reopened** task (T2, in this example) is editable/capturable
  again; the **other** task (T1) is visibly locked and its existing
  evidence is shown as "previously submitted, not available for
  preview" (not editable, not deletable).
4. Recapture real evidence for only the reopened task, reseal
   (`sealTargetedRevision`), and sync. While this is in flight, if you
   have any way to inspect bytes-on-the-wire (e.g. a proxy, or just the
   manifest's declared sizes vs. what's actually uploaded), confirm T1's
   evidence is **not** re-transmitted — it should be referenced by its
   existing ID/hash only.

### 9. Back on the dashboard: re-review, sign-off, verify

1. Confirm the revision-history panel now shows v2, with T2's evidence
   updated and T1's untouched.
2. Confirm the PC(s) under the reopened task are flagged for re-review
   (`needs_review`) and the ones under the untouched task are not.
3. Attempt sign-off with a **deliberately wrong password first** —
   confirm it's rejected (401) and nothing else changes.
4. Re-score the flagged PC(s), then sign off for real with the correct
   password. If you choose a final recommendation that differs from the
   computed one, confirm the override-reason field becomes mandatory
   (try submitting blank first — expect 422) before accepting a real
   reason.
5. Download the resulting PDF. Open the `#/verify/:reportId` page (the
   same URL the PDF's own QR code encodes — scan it with the phone's
   camera if convenient, or just navigate there in a browser) and
   confirm it shows a valid signature and the minimal safe fields only
   (no worker PII/evidence).
6. Run the offline verifier for real:
   ```
   python tools/verify_report.py <downloaded-report>.pdf --pubkey <hex-or-pem> \
     --receipt <downloaded-report>.pdf.receipt.json
   ```
   Then flip one byte of a *copy* of the PDF (`dd` or any hex editor)
   and confirm `verify_report.py` fails closed on the copy — this is the
   literal tamper-evidence guarantee P7 claims; prove it, don't take it
   on faith.

### 10. Report back

Write your findings to a new file, `docs/gates/P7_physical_device_<today's-date>.md`,
following the structure and tone of the existing
`docs/gates/P6_physical_device_2026-10-14.md` (exact device/commands
used, PASS/FAIL per numbered step above with real command output or
screenshots as evidence, any bugs found — fixed and regression-tested,
or explicitly disclosed as a known limitation if not fixed, never
silently glossed over). Save any screenshots/XML dumps/JSON captures
under a dedicated evidence directory (e.g. `/tmp/parakh-p7-<date>/`,
matching the convention this session's own `/tmp/parakh-p6-20261014/`
already used) and reference their paths in the report rather than
inlining large binary content.

Do **not** mark P7 complete yourself — that determination belongs to
the repo owner. Your job is to produce an honest, evidence-backed
PASS/FAIL record for every numbered step above, fix any real defects
you find along the way (with regression tests, not just patches), and
leave the working tree in a clean, reviewable state (no stray override
files, no leftover test containers).

=====

## Why this document exists (not part of the prompt above)

Per the task's own instructions, P7 cannot be claimed complete until
this physical-device + live-dashboard gate has actually run and its
results have been reviewed — automated test suites, however thorough,
cannot exercise Android Keystore/CameraX/MediaCodec on real hardware or
substitute for a human looking at the dashboard. This file is the
complete, standalone handoff for that gate. After it runs, read its
results, fix anything it finds, and only then revisit whether P7 can be
marked complete in `docs/gates/P7.md` and the root `README.md`.
