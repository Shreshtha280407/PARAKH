# apps/android/

Kotlin + Jetpack Compose worker app. Fully offline through P3-P5 (no
network, no backend, no worker account login); P6 adds real, resumable
sync of the P5 sealed outbox to the FastAPI backend over HTTPS, still with
no worker login -- only a device-scoped self-registration bootstrap (see
`docs/worker_capability_tokens.md`'s "Identity bootstrap (P6)" section).
P7 adds periodic polling (`data/sync/WorkerUpdatesWorker.kt`, 15-minute
`PeriodicWork`) for assessor-initiated targeted reassessment requests and
report-availability status, and — when a request lands — unlocks and
re-seals only the specific reopened task(s)
(`SealOrchestrator.sealTargetedRevision`): unchanged tasks' evidence is
reused by reference (re-declared in a new signed manifest, never
re-encrypted or re-uploaded), matching the fact that a prior revision's
synced vault files are already deleted from the device by the time a
reassessment request can arrive. Reads `packs/ae-con-q0602/` as bundled
task-pack data (synced in at build time, never hand-duplicated — see
`core/mapping/build.gradle.kts`). See `docs/gates/P3.md` / `P4.md` /
`P5.md` / `P6.md` / `P7.md` for the full scope boundary of each phase and
`docs/gates/IC1A.md` for the acceptance gate this module is held to. The
app's user-visible display name is "PARAKH"; the Android package
(`in.kaushalpramaan.app`) and internal identifiers are unchanged.

## Modules

| Module | Role |
|---|---|
| `:app` | The worker-facing Compose app (`in.kaushalpramaan.app`). Language, consent, registration, declaration, match result, task list/detail, real in-app CameraX photo/video evidence capture into a SQLCipher-encrypted Room draft store (preview, retake, replace, delete), automatic optimisation/seal/encrypted-vault-outbox (P5), resumable WorkManager sync of that sealed outbox to the server (P6, `data/sync/`), and P7's periodic worker-updates poll + task-scoped reassessment unlock/reseal/resubmit. |
| `:core:mapping` | Pure Kotlin/JVM port of `ml/mapping/matcher.py` (match-rules@r3, 20 declaration cards + 6 tools). No Android dependency — its `GoldenVectorsTest` runs as a plain fast JUnit `test` task. `:app` depends on it like any other library. |
| `:core:budget` | Pure Kotlin/JVM deterministic budget ledger (P5) — per-task/total byte accounting, no Android dependency. |
| `:core:seal` | Android library: streaming SHA-256, the canonical signed manifest, Android Keystore ECDSA signing/verification, and the Tink `StreamingAead`-encrypted vault — including P6's bounded `decryptingStream` API the sync layer reads from. |
| `:media` | Android library: real local photo/video optimisation (Media3 Transformer) to fit the task/total byte budgets (P5) — never exposes a bitrate/resolution/quality control to the worker. |

## One-time environment setup

This repo pins exact tool versions rather than assuming Android Studio is
installed:

- **JDK**: whatever's on `PATH` (built and tested here against OpenJDK 26,
  also runs in CI against Temurin 21). `core/mapping/build.gradle.kts`
  deliberately does not pin `kotlin.jvmToolchain(...)` — an explicit pin
  would force Gradle to resolve/auto-provision that exact JDK, which fails
  offline or on a runner shipping a different JDK; this module has no actual
  need for one specific major version.
- **Gradle**: wrapper-managed (`./gradlew`, Gradle 9.7.1) — no local Gradle
  install required once `gradle/wrapper/gradle-wrapper.jar` exists.
- **Android SDK**: install via `cmdline-tools`:
  ```
  sdkmanager --install "platform-tools" "platforms;android-35" "build-tools;35.0.0" \
    "system-images;android-35;google_apis;x86_64" "emulator"
  ```
  Then point `local.properties` (gitignored) at it:
  ```
  echo "sdk.dir=$ANDROID_HOME" > apps/android/local.properties
  ```
- **Emulator** (for the instrumented E2E suite only — not needed for unit
  tests or a debug build):
  ```
  avdmanager create avd --name "KaushalPramaan_API35" \
    --package "system-images;android-35;google_apis;x86_64" --device "pixel_6"
  ```
  API 35 / Google APIs x86_64 was available and used as specified. If a
  future environment lacks API 35, substitute the newest installed stable
  API level compatible with `compileSdk`/`targetSdk` in
  `app/build.gradle.kts` and note the substitution in `docs/gates/P3.md`.

## Commands

```
# Kotlin matcher parity (fast, no emulator/device needed)
./gradlew :core:mapping:test --tests "*GoldenVectorsTest*"

# Both core:mapping test suites
./gradlew :core:mapping:test

# Static checks + debug build
./gradlew lint :app:assembleDebug

# Install on a running emulator/device
./gradlew :app:installDebug

# Full instrumented E2E journey on an emulator or real device (see
# docs/gates/P3.md and docs/gates/P4.md for the exact scenarios covered:
# Hindi flow, PARTIAL/APPROPRIATE examples, real CameraX capture/replace/
# delete, SQLCipher encryption, airplane-mode)
./gradlew :app:connectedDebugAndroidTest
```

### Testing P4's real camera capture on a real device

`EvidenceCaptureFlowTest` drives one real CameraX capture through the actual
UI, which needs CAMERA/RECORD_AUDIO actually granted. Some OEM Android
builds restrict unattended (shell/UiAutomation-driven) permission granting
even for the `shell` identity — if so, that one test cleanly skips with an
`AssumptionViolatedException` explaining why (not a failure, not a false
pass; see `docs/gates/P4.md`'s notes on `GrantPermissionsViaShell`) rather
than hanging or crashing. Real capture is still fully provable by hand: run
the app on a real device, grant the permission once through the normal
in-app flow, and use it — `docs/gates/P4.md`'s manual gate is the
authoritative, human-verified record of exactly that.

## Why `core:mapping` is a plain Kotlin/JVM module, not an Android library

The master plan's own exit-test command is
`./gradlew :core:mapping:test --tests "*GoldenVectorsTest*"` — a direct
`test` task, not `testDebugUnitTest`. A plain `kotlin("jvm")` module gives
that exact task name, runs in seconds without an Android Gradle Plugin
variant/AVD/emulator, and is what both the Python matcher parity contract
(`ml/mapping/golden_vectors.jsonl`) and this module's own unit tests need —
nothing here touches an Android API.

## Single source of truth, no manual duplication

`core/mapping/build.gradle.kts`'s `syncPackResources`/`syncGoldenVectors`
tasks copy `packs/ae-con-q0602/mapping/*.json`, `packs/ae-con-q0602/tasks.json`
and `ml/mapping/golden_vectors.jsonl` into this module's resources on every
build. Kotlin and Python always read the same bytes; there is no second,
hand-maintained copy of any threshold, weight, or golden vector to drift out
of sync. Declaration card/tool **labels** shown in the Compose UI
(`app/src/main/res/values{,-hi}/card_labels.xml`) are a presentation-layer
mirror of `links.json`'s `label` field, not a second data source for the
matcher itself — the matcher never reads string resources.

## Capture/declaration/match stays offline; sync (P6) is the one real network path

P3-P5's entire worker journey (register, declare, match, capture, optimise,
seal) still needs no network at all and still works with the phone in
airplane mode — `OfflineAirplaneModeTest` (instrumented) and
`NetworkAssertions` (helper) prove this at runtime. P6 adds the one and
only real network path: syncing an already-`READY_TO_SYNC` sealed package
to the server. `app/build.gradle.kts`'s `verifyExpectedNetworkPermissions`/
`verifyMergedManifestHasExpectedNetworkPermissions` tasks (renamed from, and
replacing, the old P3-P5 "no network permission at all"
`verifyNoNetworkDependencies` check) now assert the opposite, P6-correct
policy: exactly `INTERNET` + `ACCESS_NETWORK_STATE` are declared, and
nothing else network/media/gallery/public-storage-related ever is.
`verifyReleaseForbidsCleartextTraffic` separately proves a release build
cannot use plain HTTP even once it does have that permission — see
`docs/gates/P6.md`.
