# apps/android/

Kotlin + Jetpack Compose offline worker app (P-3). Reads
`packs/ae-con-q0602/` as bundled task-pack data (synced in at build time,
never hand-duplicated — see `core/mapping/build.gradle.kts`). No backend,
no network, no worker account login for anything in this module's scope —
see `docs/gates/P3.md` for the full scope boundary and `docs/gates/IC1A.md`
for the acceptance gate this module is held to.

## Modules

| Module | Role |
|---|---|
| `:app` | The worker-facing Compose app (`in.kaushalpramaan.app`). Language, consent, registration, declaration, match result, task list/detail, mock evidence, preview, attestation, local "sealed" submit. |
| `:core:mapping` | Pure Kotlin/JVM port of `ml/mapping/matcher.py` (match-rules@r2). No Android dependency — its `GoldenVectorsTest` runs as a plain fast JUnit `test` task. `:app` depends on it like any other library. |

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

# Full instrumented E2E journey on the emulator (see docs/gates/P3.md for
# the exact scenarios this covers: Hindi flow, PARTIAL/APPROPRIATE examples,
# budget overflow rejection, delete/replace recompute, airplane-mode)
./gradlew :app:connectedDebugAndroidTest
```

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

## Offline-first, enforced at build time

`app/build.gradle.kts`'s `verifyNoNetworkDependencies` task fails the build
if `AndroidManifest.xml` ever declares `android.permission.INTERNET` or
`ACCESS_NETWORK_STATE`. No networking library is declared as a dependency
anywhere in this module. `OfflineAirplaneModeTest` (instrumented) and
`NetworkAssertions` (helper) additionally prove at runtime that the
installed app holds no INTERNET permission and that the full match →
task → evidence journey completes with the emulator in airplane mode.
