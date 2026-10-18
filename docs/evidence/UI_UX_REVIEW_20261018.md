# Parakh UI/UX review — 18 October 2026

This records the earlier `0.8.0-ui-review` delivery. The later installed version and single-attempt sync policy are documented in [the sync/language update](SYNC_UX_UPDATE_20261018.md).

The Android app and assessor dashboard now use the supplied design boards’ brown/cream palette, Fraunces headings, Noto Sans text, rounded controls, outlined cards, and screen structure. The installed app is named **Parakh**. The updated dashboard is published at [parakh-dashboard-five.vercel.app](https://parakh-dashboard-five.vercel.app/).

**Live limitation:** the hosted API reports `Reviewer email delivery is not configured. Scoring and sign-off are unavailable.` Private evidence review and reviewer actions therefore remain unavailable on the hosted service until the operator configures reviewer SMTP delivery and the reviewer allowlist. The complete private-review flow passed against the real local API/database with an isolated test email transport. No private-access restriction was removed.

## Delivered screens and behavior

| Surface | Implementation |
| --- | --- |
| Dashboard landing | Branded landing with one Enter button; no new sign-in/sign-up page |
| Assessment queue | Real submissions, status filters, paging, refresh, error recovery, empty state |
| Overview | Actual declaration/match, coverage, sync integrity, assessment status, report links |
| Evidence | Task selection, original photos, streaming videos, expanded viewer, playback/seek, quality-assistance markers, retry and clear access/storage errors |
| Scoring | Existing criterion scores, required remarks, row saves, conflict handling, competency profile; unsaved edits survive switching tabs |
| Decision | Validated reassessment instructions/task selection, rejection reasons, attestation and authorized report signing |
| Audit/history | Actual revision history, reassessment requests, and append-only audit events |
| Public queue and verification | Signed reports, report-ID lookup, truthful signature/integrity results |
| Worker onboarding | Language, consent, registration/PIN, declaration and match screens |
| Worker evidence | Task list/detail, camera/photo/video, evidence preview, retake/delete, trim, review/optimize/seal, submitted/sync screens |

Existing offline drafts, encryption, local PIN protection, evidence budgets, capture/sealing, uploads and reassessment behavior are retained. The real declaration contains 20 items and six tools; example-only data from the design boards was not substituted for real records.

Primary actions remain visible in fixed footers. Content scrolls independently. English/Hindi switching and validation remain wired to their existing functions. Camera and video views release playback/resources on exit. Granting camera/microphone permission no longer prematurely locks navigation: local data locks when the activity actually stops, rather than when a permission dialog briefly pauses it.

The header **Parakh** wordmark now uses bold Fraunces serif lettering and the supplied theme colors. The cream welcome screen also uses dark Android status-bar icons for readability.

## Logo and installed app

The original supplied PNG is preserved unchanged in both projects. Its SHA-256 is `3e597c1eca95be201ddd87ca10cff8804b547ca6b111fe4a6f4971212b889968`.

The launcher uses only the existing diagram region, cropped losslessly from `(235, 15)` to `(1095, 875)`. The baked wordmark/tagline is excluded. The diagram was not redrawn, recolored or AI-generated; its original background is retained. Dashboard rendering uses the same source region.

| Installed item | Value |
| --- | --- |
| Display name, including Hindi locale | **Parakh** |
| Application ID | `in.kaushalpramaan.app` |
| Version | `0.8.0-ui-review` / code `3` |
| Phone | USB-connected OnePlus CPH2691 |
| Backend | `https://api-production-c626.up.railway.app` |
| Signing | Android debug certificate, for review |
| APK | `/tmp/parakh-ui-review/Parakh-review.apk` |
| APK SHA-256 | `bd5e1d1d88a7bf2ab8248f2b2391c103a9652a83189ba9b357227b1b4c8066d6` |

The installed package was launched successfully to the welcome screen. The temporary QA app and its runner were removed after testing. Unrelated existing benchmark packages were left alone. Test-only storage ceilings, forced optimization, debug export, and runtime server overrides are disabled in this installed build. It uses the deployed HTTPS API, not the emulator or laptop address.

A production signing keystore was not available, so this is a debug-signed review APK rather than a signed distribution release.

## Recording size and connectivity

**The byte calculation is real.** CameraX supplies recorded bytes during video capture; finalized photo/video sizes come from the actual file on disk. The task meter shows the percentage of the task’s remaining evidence allowance, not a percentage of the phone’s storage or an upload-progress animation.

The optional debug ceiling was only 4 MB. That test control and forced-budget controls are disabled in the installed review build. A stale recording counter is now reset when starting another recording. Labels explicitly distinguish local recording size from later upload/optimization.

The reported frozen-zero display was investigated separately from final-file correctness. A stronger physical-phone check reads the actual visible label before stopping:

| Same approximately 8-second recording | Observed value |
| --- | --- |
| Midway, while still recording | `Recorded on this phone: 1.2 MB of 17.8 MB` |
| Before pressing Stop | `Recorded on this phone: 2.4 MB of 17.8 MB` |
| Final file bytes | `2,592,303` |
| Persisted evidence bytes | `2,592,303` |
| Duration | `8,090 ms` |

The visible meter increased in the updated build; a frozen zero was not reproduced in that run. The live display rounds to one decimal MB and the MP4 container is finalized after Stop, so the rounded live label is not an exact final-byte total. Photos receive their final measured size after the shutter completes. The app may produce different video sizes than a phone camera app because capture quality/bitrate and later optimization differ.

The connectivity indicator uses Android’s validated internet status. The slash appears only when internet is unavailable. Wi-Fi strength uses Android’s reported RSSI and signal-level calculation when available; mobile data has its own indicator. Unknown strength is not replaced with invented full bars. Manufacturer-specific status-bar rendering may differ from the app’s four-level display.

## Validation

| Check | Result |
| --- | --- |
| Dashboard production build | Passed locally and on Vercel |
| Dashboard lint | Passed; four warnings, no errors |
| Browser flows against local API/PostgreSQL | **9 passed** |
| Focused backend evidence/open-review regressions on PostgreSQL | **23 passed** |
| Final Android review-build unit tests | **94 passed**, zero failures/errors |
| Android assemble/lint | Passed; lint reports 40 warnings and no errors |
| Phone navigation/language/registration/declaration/match/design flow | **8 passed** |
| Phone real photo capture, preview, retake and deletion | **Passed** |
| Phone visible recording-meter growth and final byte equality | **Passed** |
| Responsive layouts | Checked at 390, 768 and 1440 px; no page overflow |

Browser media testing uploaded actual JPEG/H.264 MP4 fixtures through the resumable upload API, verified private access, opened photos and expanded video, played and sought video, checked `206` byte-range responses, and recovered from a simulated expired-access response using Retry. It also exercised scoring validation, preserved unsaved remarks, sign-off/report verification, targeted reassessment and rejection. The fixture transport and records were confined to the isolated test backend.

This is targeted flow verification, not a claim that every OS/browser combination or every possible button state has been exhaustively tested. Trim and sealing/sync retain their existing pipelines and have the new UI; a new full phone-to-production sealed submission was not performed during this review. Screenshots are available for visual review rather than a claim of an automated pixel-for-pixel comparison of every board.

## Deployment and review artifacts

Vercel project: `nipun-kalsotras-projects/parakh-dashboard` (`prj_QuZl6BmJeNFE6ZYt5ClPnBoL9IY9`). Target: **production**, status: **READY**. Deployment: `dpl_89iEYwwFN8WieiqgBZnH111kDbk3`. The staged production build was checked before promotion; its JS/CSS hashes match the locally tested build.

Deploy result: **Vite/React**, build duration **10 seconds**, post-build **8 seconds**. Published URL: https://parakh-dashboard-five.vercel.app/. The post-deployment browser check passed, including the Enter button, Fraunces wordmark, real API/queue responses and responsive widths. It reported zero browser page errors. The bounded Vercel runtime scan returned zero error records; no monitoring integration or drain was provisioned as part of this task.

The deployed API/database/storage health checks returned OK. The backend and worker still report source SHA `7800a189555e9416bc01f504777bd246c7ba4c0a`; this task did not deploy a backend change. Dashboard source was uploaded from the current uncommitted working tree based on `df6c575383afa1c61b654691d4f382ab30e1570f`. **No Git commit or push was performed.**

Post-deployment checks and installation details are recorded in [verification.json](UI_UX_REVIEW_20261018/verification.json). The bounded deployment error scan is included where available; this task did not provision monitoring integrations or log drains.

Screenshots:

- [Published dashboard landing](UI_UX_REVIEW_20261018/screenshots/dashboard-live-landing.png)
- [Dashboard queue](UI_UX_REVIEW_20261018/screenshots/dashboard-queue.png)
- [Private evidence viewer using synthetic test data](UI_UX_REVIEW_20261018/screenshots/dashboard-evidence.png)
- [Phone language/welcome](UI_UX_REVIEW_20261018/screenshots/01-language.png)
- [Phone consent](UI_UX_REVIEW_20261018/screenshots/02-consent.png)
- [Phone registration](UI_UX_REVIEW_20261018/screenshots/03-candidate-details.png)
- [Phone declaration](UI_UX_REVIEW_20261018/screenshots/04-declaration.png)
- [Phone match](UI_UX_REVIEW_20261018/screenshots/05-match-result.png)
- [Phone tasks](UI_UX_REVIEW_20261018/screenshots/06-practice-tasks.png)
- [Phone task detail](UI_UX_REVIEW_20261018/screenshots/07-task-detail.png)
- [Phone review/seal](UI_UX_REVIEW_20261018/screenshots/11-review-and-seal.png)

Phone screenshots contain synthetic QA onboarding data. Only the isolated test window temporarily allowed screenshots; the installed app retains its normal secure-window protection. Test logs in the adjacent artifact directory document the final results. APKs and temporary test databases are not added to Git.

## Rebuild the installed review variant

```sh
JAVA_HOME=/opt/android-studio/jbr ANDROID_HOME=/home/nipun/Android/Sdk \
  ./apps/android/gradlew -p apps/android :app:assembleDebug \
  -PworkerReviewBuild=true \
  -PdebugSyncBaseUrl=https://api-production-c626.up.railway.app \
  -PreleaseVersionCode=3 -PreleaseVersionName=0.8.0-ui-review \
  --no-daemon --max-workers=2 --offline
```

Review the screenshots and working-tree changes before your manual commit/push. Configure the hosted reviewer email service before expecting private dashboard review and sign-off to work on production.
