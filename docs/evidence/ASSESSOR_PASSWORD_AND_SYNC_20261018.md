# Parakh assessor access, navigation and sync update — 18 October 2026

Latest dashboard follow-up: [Decision confirmations, review speed, scoring and history](DASHBOARD_REVIEW_UPDATE_20261018.md).

The requested changes are implemented, deployed and installed. The dashboard now uses assessor password accounts instead of its email-code gate. The phone has **Parakh 0.8.2-sync-review**, version code **5**, installed in place with existing data preserved.

## Assessor form and password confirmations

- Opening an assessment while signed out opens a form for **full name, email, phone number and password**. Existing assessors can select **Already registered? Sign in**.
- Before the fields, a highlighted reminder says **“Remember your password”**, explains that there is **no forgot-password or password reset option**, and says the password is required for signing, rejection and reassessment suggestions. Creating an account requires acknowledging this reminder.
- As requested, anyone can create an assessor account. An active assessor session can review submitted candidate assessments, open private evidence and score criteria across the dashboard.
- Signing, rejecting and requesting targeted reassessment each require entering the account password again and explicitly confirming the action. The backend verifies that password on every request, including repeated sign-off requests. Missing or incorrect passwords do not change the assessment.
- Passwords use the existing Argon2 password hashing implementation. Random session tokens are stored hashed server-side and delivered through secure HttpOnly cookies. Mutations require CSRF confirmation. Sessions expire after eight hours; logout revokes the server session. Passwords are never stored in browser storage.
- Names, email addresses and phones are self-declared; this flow does not claim email ownership verification. Private audit and signed-report identity snapshots distinguish password accounts from legacy email-verified reviewers. Worker tokens and existing organizational/admin API permissions remain separate.

## Persistent dashboard navigation

Queue, Public queue and Verify report remain visible on every dashboard page. The active option is highlighted and marked with `aria-current`, including assessment detail and individual report verification routes. The alternate top-right “Enter dashboard” return link is removed. Desktop and 390-pixel layouts were checked for horizontal overflow.

## Sync circle and phone update

The connected phone has animator, transition and window animation scales set to zero. That stopped the standard animated spinner. The sync circle now uses frame timestamps so it continues moving independently of those device animation settings. Queued uploads and manual retries show activity; failed, cancelled, stalled and completed states stop it. A running manual retry also takes precedence over error rows left by its previous attempt.

The upload byte meter still uses actual acknowledged bytes. **Only the first attempt after sealing is automatic. Failed attempts still require Retry syncing**, even after internet returns.

The main app was updated using `adb install -r`, retaining its existing application ID, signing identity, diagram-only launcher icon, name **Parakh**, data and live backend URL. The isolated QA app and test runner were removed, and the main app was opened after installation.

## Verification

| Check | Result |
|---|---|
| Android unit suite | 106 passed, zero failures/errors/skips |
| Physical-phone spinner check | Passed: pixels change while active, stop on failure/completion and restart after Retry, with device animation scale zero |
| Android build and lint | Successful; zero errors/fatals, 54 warnings |
| Backend tests on separate local PostgreSQL database | 26 passed |
| Full local browser integration | 12 checks passed |
| Deployed browser/API integration | 4 checks passed, zero JavaScript errors |
| Migration on temporary Neon branch and deployed staging database | Both reached `e53a28c09b12`; assessment counts preserved |

Local browser checks include account creation and required reminder acknowledgement, session restoration, password sign-in after logout, rejection of incorrect passwords for all three final actions, real private photo/video opening and seeking, media retry, scoring, report signing/public verification and worker-facing targeted reassessment. Local tests use synthetic candidate/media fixtures; they do not create cloud candidate submissions.

Live checks exercised the real deployed form, successful account creation and private review access, secure cookies, CSRF rejection, logout, incorrect-password rejection, successful password sign-in, public navigation and API/database/storage health. They created **one clearly named synthetic assessor account** and **zero candidate assessments or assessment decisions**. Consequential decision tests ran against the isolated local database.

## Deployment and review artifacts

- Dashboard: https://parakh-dashboard-five.vercel.app/
- Vercel deployment: `dpl_2TT1Qh6YfV6PHWN3u8DwFgqSJraU`.
- Railway API deployment: `740b0810-fa42-46f3-862a-5b487f815ef5`.
- Database migration: `e53a28c09b12`, additive account/session tables; no existing assessment deletion or relabelling.
- Migration-test branch: `br-aged-base-b3on6qtj`, scheduled to expire on **19 October 2026 at 12:46:17 UTC**. Local environment credentials were not repointed to it.
- Install and source checksums: [verification.json](ASSESSOR_PASSWORD_AND_SYNC_20261018/verification.json).
- Main review APK: `/tmp/parakh-ui-review/Parakh-0.8.2-sync-review.apk` (debug-signed review build, live API).
- Screenshots: [assessor form](ASSESSOR_PASSWORD_AND_SYNC_20261018/screenshots/live-assessor-form.png), [mobile form](ASSESSOR_PASSWORD_AND_SYNC_20261018/screenshots/live-assessor-form-mobile.png), [desktop navigation](ASSESSOR_PASSWORD_AND_SYNC_20261018/screenshots/live-navigation-1440.png), [mobile navigation](ASSESSOR_PASSWORD_AND_SYNC_20261018/screenshots/live-navigation-390.png).

Deployment uses the uncommitted review source, with its content checksum recorded separately from the base Git commit. No Git commit or push was made. The email-delivery limitation in earlier reports no longer blocks the current assessor account flow.
