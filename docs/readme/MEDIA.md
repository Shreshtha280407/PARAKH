# README media and capture notes

The README uses the supplied PARAKH logo, actual application screens, real browser recordings and code-native diagrams. No generated photograph or fabricated interface is used as product evidence.

## What each visual shows

| Asset | Origin | Presentation |
|---|---|---|
| [Cinematic hero](../assets/readme/hero.gif) | Real phone and local dashboard captures; existing app logo derived from the supplied artwork | An animated HTML/CSS composition, not an end-to-end recording |
| [Worker walkthrough](../assets/readme/worker-journey.gif) | USB screenshots from a OnePlus 13R | A six-scene sequence of real screens from the isolated QA app |
| [Assessor recording](../assets/readme/assessor-review.mp4) | Playwright against the real local frontend and API | Browser recording using sample candidates and test media |
| [Live-site tour](../assets/readme/live-product-tour.mp4) | The supplied public Vercel URL | Read-only browser recording of the deployed landing page |
| [Worker gallery](../assets/readme/worker-gallery.webp), [evidence gallery](../assets/readme/evidence-gallery.webp) | The same USB captures | HTML/CSS compositions; phone status bars are cropped |
| [Assessor gallery](../assets/readme/assessor-gallery.webp) | The same real local dashboard flow | Four screens presented together, with explanatory captions |
| [Report verification](../assets/readme/report-verification.webp) | A real signed report generated through the local API | Anonymous verification of the stored sample report |
| Architecture, workflow, pipeline, reassessment and budget diagrams | Repository implementation and supplied project references | Accessible SVGs generated from code; the technical sequence is Mermaid |

The logo supplied by the owner is preserved at [docs/assets/brand/parakh-logo.png](../assets/brand/parakh-logo.png). Its checkerboard is part of the original RGB image, not a transparent background. The existing product logo has the same artwork; no logo redesign or background removal was performed.

The phone screenshots were captured on 20 October 2026 using a separate application ID, `in.kaushalpramaan.app.p8validation`. The existing production app and its data were retained. Screenshot protection is relaxed inside the QA instrumentation only; the production `FLAG_SECURE` behavior was not changed. The recording screen UI is the production source compiled into that separate package.

The app walkthrough ends at review before sealing. It does not demonstrate a completed practical task or a newly sealed package. The assessor flow uses the repository's explicit media fixtures, including a test image and color-bar video. Scripted scores demonstrate report issuance mechanics, not a worker's competence. The targeted reassessment dialog is filled and cancelled in this capture; actual task recapture/revision evidence is linked separately in the implementation index.

Direct phone screen recording did not produce a usable stream on this device. The worker animation therefore uses the successful USB screenshots. The dashboard and live-site clips are actual Playwright screen recordings.

## Reproduce the captures

Requirements: the existing backend virtual environment, dashboard dependencies including Playwright, Chromium, FFmpeg, a configured Android SDK/JDK, and a USB-authorized Android device. Artwork rendering uses the local Space Grotesk and Liberation Serif fonts; change the paths in the renderer if those fonts are elsewhere.

From the repository root, start the isolated capture API:

```bash
server/.venv/bin/python tools/readme/serve_capture.py
```

In a second terminal, start the dashboard against it:

```bash
cd apps/dashboard
VITE_API_BASE_URL=http://127.0.0.1:18198 npm run dev -- --host 127.0.0.1 --port 18197
```

The API binds to loopback, uses `/tmp/parakh-readme-capture/capture.sqlite3`, stores evidence privately under that temporary directory, and creates its own persistent local-only report key. It does not read cloud credentials. This is a documentation capture setup, not a production deployment or concurrency test.

Run the browser capture from the root:

```bash
node tools/readme/capture.mjs
```

It records the public landing page read-only. All sample enrollment, review, scoring and signing operations use the fixed loopback API. Repeated captures add sample records to that disposable database and remain subject to the application's actual throttling. A run with `SKIP_LIVE=1` skips the live-site tour.

For phone screens, build and install **only the separate QA package**:

```bash
cd apps/android
./gradlew -Pp8Validation=true -PworkerReviewBuild=true \
  :app:assembleDebug :app:assembleDebugAndroidTest
cd ../..
adb install -r apps/android/app/build/outputs/apk/debug/app-debug.apk
adb install -r apps/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell am instrument -w \
  -e class in.kaushalpramaan.app.ReadmeCaptureTest \
  in.kaushalpramaan.app.p8validation.test/androidx.test.runner.AndroidJUnitRunner
adb exec-out run-as in.kaushalpramaan.app.p8validation \
  tar -cf - files/readme-captures > /tmp/parakh-readme-phone-captures.tar
```

The capture driver resets the **QA app's** local draft and enters sample onboarding data. Extract the PNG files from the archive into `docs/assets/readme/`, using each file's basename. Never run data-clearing capture helpers against a candidate's production package.

Build the artwork and delivery formats:

```bash
python3 tools/readme/diagrams.py
node tools/readme/artwork.mjs
python3 tools/readme/media.py
```

The optional `PARAKH_LOGO_SOURCE` environment variable tells the artwork script where to copy the owner's original logo if it is not already preserved. The hero uses the logo already bundled with the product. Intermediate animation frames live under `/tmp/parakh-readme-artwork/`.

The encoders produce inline GIFs, compressed WebP stills, and H.264 MP4 recordings. Raw PNG/WebM sources are temporary intermediates; the repository keeps the delivery formats and capture tooling. The visual order is editorial; no product result is painted into a screenshot.

## Evidence and review

The [capture manifest](../assets/readme/capture-manifest.json) records the source URL, sample-data boundary, successful API/browser checks and JavaScript errors. The [asset inventory](../assets/readme/asset-manifest.json) lists delivery-file sizes and SHA-256 digests. [Implementation status](IMPLEMENTATION_STATUS.md) separates these fresh documentation checks from historical product gates.

Static alternatives are available for motion-free review: [hero](../assets/readme/hero-poster.webp), [worker screens](../assets/readme/worker-gallery.webp), [dashboard screens](../assets/readme/assessor-gallery.webp), and [live landing](../assets/readme/live-landing.webp).
