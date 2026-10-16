# Q4 / P8 physical-device reproduction

Use three explicitly identified phones: entry, mid-range and the available OnePlus 13R.
Record manufacturer/model, Android/API version, serial locally, run ID, source stamp and
APK SHA-256. The OnePlus 13R is a flagship; it cannot satisfy entry/mid-range gates.
Do not uninstall, clear app data, reset a database or run the entire legacy UI suite on a
personal phone. `TestFlows` in that suite intentionally resets the production draft DB.
Use the isolated classes below for automated regression. Confirm the exact device and
`in.kaushalpramaan.app` / `in.kaushalpramaan.app.test` before any `install -r` update.

## Build and safe isolated tests

From the repository root:

```sh
git status --short
git branch --show-current
git log -5 --oneline
cd apps/android
./gradlew :app:assembleDebug :app:assembleRelease :app:assembleDebugAndroidTest \
  :app:check :core:seal:testDebugUnitTest :media:testDebugUnitTest \
  :assist-quality:testDebugUnitTest :assist-hands:testDebugUnitTest --console=plain
cd ../..
python3 tools/verify_assistance_assets.py --require-calibrated \
  --apk apps/android/app/build/outputs/apk/debug/app-debug.apk \
  --apk apps/android/app/build/outputs/apk/release/app-release-unsigned.apk
adb devices -l
```

After target/package confirmation, replace `SERIAL` with that exact target:

```sh
adb -s SERIAL install -r apps/android/app/build/outputs/apk/debug/app-debug.apk
adb -s SERIAL install -r apps/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb -s SERIAL shell am instrument -w -r \
  -e class in.kaushalpramaan.app.AssistanceIntegrationInstrumentedTest,in.kaushalpramaan.app.AssistanceMigrationInstrumentedTest,in.kaushalpramaan.app.AssistanceUiInstrumentedTest,in.kaushalpramaan.app.SealOrchestratorInstrumentedTest,in.kaushalpramaan.app.data.sync.SyncRepositoryInstrumentedTest,in.kaushalpramaan.app.data.sync.WorkerUpdatesRepositoryInstrumentedTest,in.kaushalpramaan.app.AssistanceWorkManagerInstrumentedTest \
  in.kaushalpramaan.app.test/androidx.test.runner.AndroidJUnitRunner
```

These 22 tests use unique databases/synthetic evidence, package metadata inspection or a Compose component host that
never opens the production database. The encrypted v5→v6 migration
preserves populated seal/outbox/reassessment rows. P6's plaintext scan compares pre-existing
matching file hashes, detecting new/changed copies without deleting legitimate drafts.
It is an end-state disk scan, not proof that a transient copy never existed.

For offline proof, record the original airplane/Wi-Fi/mobile-data settings, enable airplane
mode, disable Wi-Fi if necessary and wait until `dumpsys connectivity` reports no active
internet network. Rerun the same command with `-e p8RequireOffline true`; both native
inference tests assert that no network has INTERNET capability. Restore the recorded
settings afterward. A settings toggle alone is insufficient proof: disconnection is
asynchronous. Do not publish full connectivity dumps containing addresses/subscription data.

## Native signing → real backend → targeted reassessment → browser

Start the isolated stack (never reads root `.env`, never uses the main MVP volumes):

```sh
docker compose -f infra/docker-compose.p8-test.yml up -d --build
docker compose -f infra/docker-compose.p8-test.yml exec -T api python -m app.seed
adb -s SERIAL reverse tcp:18008 tcp:18008
adb -s SERIAL shell am instrument -w -r \
  -e p8ApiBaseUrl http://127.0.0.1:18008 \
  -e class in.kaushalpramaan.app.AssistanceUploadInstrumentedTest \
  in.kaushalpramaan.app.test/androidx.test.runner.AndroidJUnitRunner > /tmp/p8-native.log
python3 - <<'PY'
import json
from pathlib import Path
line = next(s for s in Path('/tmp/p8-native.log').read_text().splitlines()
            if s.startswith('INSTRUMENTATION_STATUS: p8NativeResult='))
Path('/tmp/p8-native.json').write_text(json.dumps(json.loads(line.split('=', 1)[1]), indent=2) + '\n')
PY
cd apps/dashboard
npm ci
npx playwright install --with-deps chrome
P8_NATIVE_FIXTURE=/tmp/p8-native.json node e2e/p8-native.mjs
cd ../..
adb -s SERIAL reverse --remove tcp:18008
```

The test refuses non-loopback endpoints and ports other than 18008. It uses the isolated
test assessor credentials from that Compose file. Native Q2/Q3 results are frozen by real
P5/Android Keystore signing, uploaded through production `SyncRepository`, retrieved by
authenticated API, compared to their frozen snapshots and reviewed after an explicit test
assessor requests T2 reassessment. T1 remains inherited with its original snapshot. The
browser seeks actual native-generated intervals. No private recordings are used.
This test calls production repository/analysis/seal/sync APIs with synthetic files;
it does **not** automate CameraX capture, Compose navigation or actual WorkManager execution.
Together with that separate real-backend test, the selected physical set contains 23 tests.
The separate WorkManager test executes the real production worker and analyzers after
repository finalisation. A WorkerFactory supplies only its isolated encrypted database;
the normal two-argument production constructor remains available. WorkManager uses an
in-memory test database, and no existing production jobs are cancelled. Both photo/video
results persist and repeated scheduling preserves their completed generation. This proves
native background execution. The separate October 16 QA-UID run below now also verifies
real OS process-stop/restart recovery; it does not retrofit that claim onto these earlier tests.
`P8_CHROME=/absolute/path/to/chrome` may select an already installed browser instead of
installing Chrome. Both browser harnesses support that override and otherwise use
the Chrome channel for actual H.264 playback; media codec support is required by these tests.

If cached Docker images exist but registry DNS is unavailable, the documented local fallback is:

```sh
cd apps/dashboard
VITE_API_BASE_URL=http://127.0.0.1:18008 npm run build
cd ../..
docker compose -f infra/docker-compose.p8-test.yml -f infra/docker-compose.p8-local.yml \
  up -d --no-build --pull never
```

This mounts current server sources/migrations and the built dashboard read-only into cached
images. It is a current-source test, not a successful fresh-image build.

## Product UI / field run

An opt-in QA build now provides a separate app UID for the actual product-screen run.
It uses the same production navigation, CameraX, encrypted Room, native analyzers and
OS WorkManager. Only this build adds a read-only state observer (no exported endpoints).
The observer adds polling overhead; never use this build for inference performance claims.
No data-clearing rule is used. Normal debug/release builds omit these QA sources.
Confirm the device and **both new packages** before installing:
`in.kaushalpramaan.app.p8validation` and `in.kaushalpramaan.app.p8validation.test`.
Position a privacy-safe scene before capture; recordings stay outside Git.

```sh
cd apps/android
./gradlew -Pp8Validation=true :app:assembleDebug :app:assembleDebugAndroidTest \
  :app:verifyMergedManifestHasExpectedNetworkPermissions --console=plain
cp app/build/outputs/apk/debug/app-debug.apk /tmp/p8-ui-app.apk
cp app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk /tmp/p8-ui-test.apk
# Build a separate runtime APK, preserving the UI pair above.
./gradlew -Pp8Validation=true -Pp8ValidationShrink=true :app:assembleDebug --console=plain
cp app/build/outputs/apk/debug/app-debug.apk /tmp/p8-r8-app.apk
cd ../..
python3 tools/verify_assistance_assets.py --require-calibrated \
  --apk apps/android/app/build/outputs/apk/debug/app-debug.apk
# These APKs are separately named PACKAGES, although Gradle's output filenames
# are still app-debug*.apk. Rebuild without the property for normal debug APKs.
adb -s SERIAL install -r /tmp/p8-ui-app.apk
adb -s SERIAL install -r /tmp/p8-ui-test.apk
```

Record original connectivity settings, disconnect, then run these ordered phases.
`intake` requires a fresh QA assessment and refuses to erase an existing one.
Each phase drives real controls; the host reads redacted observer JSON without restarting
instrumentation during worker recovery. `recovery` deliberately stops only the QA UID
after real inference is RUNNING and final-preview navigation has succeeded, then launches
the normal app and verifies completion against the same hash/evidence/revision.
The interrupted JUnit invocation is recorded as an expected stop, never as a passed test.

```sh
python3 tools/p8_device_ui.py --serial SERIAL --phase intake --require-offline --out /tmp/p8-ui-intake.json
python3 tools/p8_device_ui.py --serial SERIAL --phase photo-retake-delete --require-offline --out /tmp/p8-ui-photo.json
python3 tools/p8_device_ui.py --serial SERIAL --phase recovery --seconds 45 --require-offline \
  --r8-apk /tmp/p8-r8-app.apk --out /tmp/p8-ui-recovery.json
# Restore the unshrunk UI target before running more Compose instrumentation.
adb -s SERIAL install -r /tmp/p8-ui-app.apk
python3 tools/p8_device_ui.py --serial SERIAL --phase inspect --require-offline --out /tmp/p8-ui-inspect.json
python3 tools/p8_device_ui.py --serial SERIAL --phase seal --require-offline --out /tmp/p8-ui-seal.json
# Verify syncWork is ENQUEUED with CONNECTED constraint, no server identity,
# no uploaded bytes, and all sealedSnapshot fields remain immutable offline.
adb -s SERIAL reverse tcp:18008 tcp:18008
# Restore original connectivity settings; wait for a real active network.
python3 tools/p8_device_ui.py --serial SERIAL --phase synced --out /tmp/p8-ui-synced.json
adb -s SERIAL reverse --remove tcp:18008
```

The QA default sync URL is the isolated localhost:18008 test backend; release's HTTPS
policy and normal debug endpoint are unchanged. Compare each exact sealedSnapshot with
the authenticated assessor response before claiming offline exit E. All unavailable
devices and independent bad/good field captures still require their separate runs.

Compose instrumentation runs against the production-equivalent nonshrunk target. R8
runtime validation is separate: the host stops the real RUNNING worker, updates the same
QA package with the shrunk APK without clearing data, launches the normal product Activity
and observes real offline native completion. No broad keep rules retain test-only library
APIs. Trying the cross-APK Compose harness against a shrunk target exposed missing shared
stdlib/coroutine APIs before UI execution; those attempts are failures, not passed tests.
Build the final pair from the same sources and retain both embedded stamps and hashes.
If fixes require separate iterations, record each actual stamp rather than claiming identical
binaries. The October 16 record does this explicitly.

After sync, run the existing dashboard against the actual CameraX records:

```sh
cd apps/dashboard
P8_DEVICE_SEALED=/tmp/p8-ui-seal.json P8_DEVICE_SYNCED=/tmp/p8-ui-synced.json \
  node e2e/p8-device.mjs
```

This compares every signed snapshot with authenticated persisted API data and the
post-sync phone snapshot, seeks actual markers using mouse and keyboard, and checks
360px layout and the absence of decision mutations. It does not label field accuracy.

## Controlled upload interruption and P7 product revision

For a deterministic opportunity to terminate after a received chunk, use the transparent
loopback cap. This changes timing only; it does not rewrite signed bytes or server data.
Run in a separate terminal and stop it with Ctrl-C after testing:

```sh
python3 tools/p8_network_proxy.py --upload-bytes-per-second 1048576
```

After offline sealing, before restoring connectivity:

```sh
adb -s SERIAL reverse tcp:18008 tcp:18009
python3 tools/p8_device_ui.py --serial SERIAL --phase sync-interrupt --out /tmp/p8-ui-interrupted-sync.json
# While this command waits, restore recorded phone connectivity in another terminal.
# The host stops ONLY the QA package after actual evidence-chunk progress, reopens
# it and verifies the same server assessment and exact frozen snapshots after sync.
python3 tools/p8_device_ui.py --serial SERIAL --phase synced --out /tmp/p8-ui-synced.json
```

Request reassessment explicitly as the test assessor. This is a human test action, never
triggered by assistance. Use the existing dashboard reassessment control for T2, or this
same existing authenticated API (tokens are kept only in memory):

```sh
python3 - <<'PYREQUEST'
import json, urllib.request
base = 'http://127.0.0.1:18008'
aid = json.load(open('/tmp/p8-ui-synced.json'))['state']['serverAssessmentId']
def call(method, path, data=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(base + path,
        data=json.dumps(data).encode() if data else None, headers=headers, method=method)
    with urllib.request.urlopen(request) as response:
        body = response.read()
    return json.loads(body) if body else None
token = call('POST', '/auth/login', {'email': 'p8-assessor@parakh.test',
    'password': 'p8-isolated-test-only'})['access_token']
call('POST', f'/assessments/{aid}/start-review', token=token)
call('POST', f'/assessments/{aid}/reassessment-requests', {'task_codes': ['T2'],
    'reason': 'P8 physical CameraX targeted revision test',
    'capture_instructions': 'Recapture T2 only'}, token)
print('Explicit test-assessor T2 reassessment requested')
PYREQUEST
python3 tools/p8_device_ui.py --serial SERIAL --phase check-updates --out /tmp/p8-ui-p7-updates.json
python3 tools/p8_device_ui.py --serial SERIAL --phase video --task T2 --seconds 3 --out /tmp/p8-ui-p7-video.json
python3 tools/p8_device_ui.py --serial SERIAL --phase inspect --task T2 --out /tmp/p8-ui-p7-inspect.json
# Record settings/disconnect again; wait for zero INTERNET-capable networks:
python3 tools/p8_device_ui.py --serial SERIAL --phase seal --require-offline --out /tmp/p8-ui-p7-seal.json
# Restore recorded connectivity; keep the existing reverse route until synced:
python3 tools/p8_device_ui.py --serial SERIAL --phase synced --out /tmp/p8-ui-p7-synced.json
cd apps/dashboard
P8_DEVICE_SEALED=/tmp/p8-ui-p7-seal.json P8_DEVICE_SYNCED=/tmp/p8-ui-p7-synced.json node e2e/p8-device.mjs
cd ../..
adb -s SERIAL reverse --remove tcp:18008
```

The UI harness requires the unshrunk QA UI/test pair. For independent R8 retry/recovery,
use `--phase retry-recovery --task T2 --require-offline` on an **editable** partial/failed/
unavailable item, with the shrunk runtime installed. It taps the real Retry analysis control,
changes generation, waits for RUNNING, terminates/reopens the QA process, and requires
positive analysed samples from both engines against the same evidence/hash/revision.
Never reopen or modify sealed snapshots merely to repeat an inference test.

The optional private model-init diagnostic touches only QA diagnostic files. With no queued/
running analysis, `adb -s SERIAL shell run-as in.kaushalpramaan.app.p8validation touch
files/p8-native-probe.request` requests initialization of the existing bundled CPU model.
Read `files/p8-native-probe.txt` after the request disappears; `MODEL_INITIALISED` proves
initialization only, not sampled inference. No result/database/media is changed.

The [October 16 report](../evidence/IC2_Q4_P8_20261016.md) records actual CameraX results,
failed attempts, native fixes, two signed revisions and the final original-app reinstall
requested by the owner. Missing devices and independently labelled captures remain required.

## Remaining representative field collection

Use a designated new synthetic worker assessment without touching existing assessments.
Use app CameraX capture, evidence preview, final review, attestation/seal and sync controls.
Use a reachable local test server via the existing **debug-only** sync endpoint setting;
release requires the configured HTTPS endpoint. Do not put implementation switches into
normal worker flows. Record each scenario independently on each phone:

| # | Scenario | Required observation |
|---|---|---|
| 1 | Clean photo | Preview/status responsive; capture retained regardless of advice |
| 2 | Dark photo | Actual dark warning after analysis; inspect/retake/continue available |
| 3 | Blurred photo | Record actual result and any false negative; no relabelling |
| 4 | Good video | Background progress and navigation work; record false warnings |
| 5 | Dark video | Source-relative dark intervals agree with footage |
| 6 | Blurred video | Blur intervals rendered with heuristic limitations disclosed |
| 7 | Camera movement | Motion intervals; intentional pan can also trigger advice |
| 8 | Hands visible | Record misses as misses, never relabel truth from model output |
| 9 | Hands not detected | Advisory wording; no assertion of physical absence/competency |
| 10 | Unavailable analysis | Continue/seal remains available; unavailable is not a bad capture |
| 11 | Interrupted analysis | Navigate/rotate, stop process, relaunch; durable state recovers |
| 12 | Retake before completion | Old completion never appears on replacement evidence |
| 13 | Delete during analysis | No resurrected row/file or late warning on another item |
| 14 | Optimise/trim before sealing | Hash/duration changes trigger fresh analysis or honest pending snapshot |
| 15 | Seal while analysis pending | Seal finishes; immutable signed pending state remains after late completion |
| 16 | Offline capture then later sync | No internet during capture/inference; local flags persist; sync waits for connectivity |
| 17 | Interrupt upload and resume | Same signed bytes/IDs; received bytes resume; no duplicate evidence |
| 18 | Assessor timeline | Authenticated existing player, actual duration, markers seek correct milliseconds |
| 19 | Targeted reassessment | Assessor explicitly reopens T2; only permitted tasks editable; fresh T2 analysis |
| 20 | Historical/current revisions | Old flags unchanged, new flags isolated; signed report unaffected |

Measure capture-finalised→complete, analysis wall time, process PSS sampling, sealing
latency, manifest size and upload overhead. Keep integration timing separate from library
inference. Do not reduce sampling or resolution for a faster result. Record actual wall
time; no runtime estimate is promised by the UI. Check phone responsiveness during analysis.

## Original P8 exit A/B and independent evaluation

Before inference, independently label ten deliberately bad and ten genuinely good **new**
CameraX captures. Retain every result, including unexpected warnings and missed problems.
Do not select from calibration samples or replace failed cases. Store private media outside
Git; collect only redacted scalar results and signed snapshots for the acceptance harness.
One JSONL row per capture must contain:

```text
captureId, expected (bad|good), newUnseen, labelledBeforeAnalysis, productCapture,
deviceModel, androidVersion, runId, sourceRevision, assistance (exact frozen snapshot)
```

```sh
server/.venv/bin/python tools/p8_acceptance.py --captures /private/p8-field.jsonl \
  --out /tmp/p8-field-report.json
```

The harness requires 20 distinct captures/hashes, ten labels of each kind and full
provenance; pending/unavailable or reused inputs cannot pass. Review provenance independently:
boolean declarations alone do not prove collection independence. A requires ≥8 bad flags;
B allows ≤1 good false warning. C uses the persisted browser harness and actual recorded
intervals; D requires actual worker submission despite warnings/unavailability; E requires
disconnected capture/inference followed by connectivity-constrained sync and snapshot equality.
Unrun scenarios remain NOT VERIFIED. Three-phone Q4 and independent IC-2 holdout/device-tier
acceptance remain separate requirements, even when the synthetic integration tests pass.
