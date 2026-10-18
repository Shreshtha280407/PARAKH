# Parakh sync and language update — 18 October 2026

See the newer [assessor access, navigation and spinner update](ASSESSOR_PASSWORD_AND_SYNC_20261018.md) for the currently deployed dashboard and phone version.

This update follows the final requested policy: **one automatic sync attempt after sealing; every retry after failure requires a user tap.** Internet returning, changing screens or reopening the app does not start another failed attempt.

## Changes

- The language chip displays **EN ⇄ हि** in English and **हि ⇄ EN** in Hindi.
- Sealing explicitly schedules the first upload before navigating to the sealed screen. The persisted attempt marker prevents repeated automatic scheduling, including after old WorkManager history is pruned.
- The sealed screen immediately shows a sync card. The review/seal screen shows the same card at the top, above evidence and storage usage.
- The card distinguishes queued, uploading, verifying, offline, failed, stalled and server-confirmed states. It uses the actual WorkManager state and acknowledged byte counts, with B/KB displayed for small uploads.
- A prominent **Retry syncing** button starts a new attempt after failure. Ordinary repeated taps do not create duplicate active uploads. A visibly stalled request can be explicitly restarted, with repository serialization protecting against concurrent writes.
- Uploading shows an animated activity indicator and real byte progress. Sending all bytes changes the state to verification; it does not claim the assessment has been submitted yet.
- Each failed attempt shows a popup with retry guidance. Completion shows a confirmation popup after the server accepts submission. The persistent card remains available after dismissing either popup.
- Offline failure keeps the sealed package locally. The message instructs the user to connect and tap Retry, and warns that erasing the package cancels pending uploads.
- A submit conflict is now resolved against server state before displaying success. An arbitrary HTTP 409 can no longer be treated as a confirmed submission.
- Explicit retries close idle HTTP connections before starting, avoiding reuse of a connection closed by the server while the user was reading a failure message.

## Verification

Final checks passed: **104 unit tests**, **one full phone UI/server sync flow**, **five encrypted-upload regression tests**, and Android assemble/lint. The phone flow made the first attempt automatically, kept failures stopped across relaunch, showed a popup for a second manual failure, then accepted an explicit retry through server submission and the success popup. The isolated backend confirmed assessment `20` as submitted. Its upload-open counter was four: two deliberate failures, then a manifest and evidence session in the successful attempt.

The installation receipt and screenshots are recorded in [verification.json](SYNC_UX_UPDATE_20261018/verification.json). Phone integration checks use a separate QA package, a synthetic JPEG fixture, real encrypted Room/vault/sealing and a real local FastAPI/PostgreSQL backend with controlled failures/latency. They do not create production submissions or erase the main app’s data.

The tests cover the first automatic attempt, a failed request, a failure popup, remaining stopped after relaunch and restored server availability, explicit retry, live progress, server submission, a completion popup, and language-chip ordering. Separate encrypted-upload checks exercise resumability, rejected evidence, successful uploads and submission-conflict confirmation.

The main APK was installed successfully in place as **Parakh**, version `0.8.1-sync-review`, code `4`, using the existing application ID and signing certificate. The main app’s data was preserved. Its server remains `https://api-production-c626.up.railway.app`. It is a debug-signed review build with test-only size limits and endpoint overrides disabled. The temporary QA app, runner and USB test mapping were removed.

Screenshots: [failure popup](SYNC_UX_UPDATE_20261018/screenshots/01-sync-failed-popup.png), [retry card](SYNC_UX_UPDATE_20261018/screenshots/02-sync-failed-card.png), [sync above evidence](SYNC_UX_UPDATE_20261018/screenshots/03-sync-running.png), [completion popup](SYNC_UX_UPDATE_20261018/screenshots/04-sync-completed-popup.png), [confirmed status](SYNC_UX_UPDATE_20261018/screenshots/05-sync-completed-card.png).

The deployed dashboard and backend were not changed by this Android update. The previously reported hosted reviewer-email configuration limitation still applies to private review/scoring/sign-off. Local phone-to-server testing does not establish a new production submission from the user’s phone.

No Git commit or push is part of this update.

## Build the review APK

```sh
JAVA_HOME=/opt/android-studio/jbr ANDROID_HOME=/home/nipun/Android/Sdk \
  ./apps/android/gradlew -p apps/android :app:assembleDebug \
  -PworkerReviewBuild=true \
  -PdebugSyncBaseUrl=https://api-production-c626.up.railway.app \
  -PreleaseVersionCode=4 -PreleaseVersionName=0.8.1-sync-review \
  --no-daemon --max-workers=2 --offline
```
