# Q2/Q3 original-IC-2 recovery iteration — 2026-10-15

**Update (same day, device-verified addendum)**: the owner connected the previously-used
OnePlus 13R (CPH2691) mid-session. Everything below the original report (Sections A–G) is
unchanged; this addendum adds real on-device evidence that was explicitly marked "NOT
VERIFIED" below, and reports an honest, unsuccessful real attempt to clear the remaining two
gates. See [Addendum](#addendum-device-verified-2026-10-15) at the end of this document.


Status: **partial recovery, independently measured; original IC-2/P8 gates remain not fully
met.** This document is a new, separate iteration layered on top of the already-completed,
owner-approved amended-scope gate recorded in
[Q2_Q3_acceptance.md](Q2_Q3_acceptance.md) (2026-10-14). It does not reopen, weaken, or
reinterpret that record — the amended-scope PASS there stands unchanged, and every number in
it is reproduced verbatim below as "Original (v2)". This document instead reports a new attempt
to close the gap to the **original**, stricter Master Plan IC-2 bar that the owner-amended scope
had explicitly left unaccepted (not merely deferred).

Source identity: branch `feature/q2-q3-quality-hands`, base `36e0178`, prior assistance tree
SHA-256 `66b49e8e…`. This iteration's new/changed source files and their resulting hashes are
listed in [Section F](#f-provenance). No commit/push/PR was made; no existing evidence file was
modified or deleted.

## A. Root-cause report

### Q2 video quality precision (60.7% → investigated and fixed at the aggregation layer)

`QualityAnalyzer` (Kotlin) never produced a "bad capture" verdict at all — it only emits
per-sample DARK/BLURRY/CAMERA_MOTION flags and per-condition time intervals. The 60.7%/100%
precision/recall figure came entirely from the **evaluation harness's reference interpretation
policy**, `technical_prediction()` in `ml/assistance/protocol.py`: a video-level anchor is
"bad" if DARK **or** BLURRY **or** CAMERA_MOTION fires at that 1-second anchor (OR'd, with no
run-length requirement), and the clip is "bad" if the **fraction** of bad anchors is ≥ 0.2 —
with no distinction between one isolated noisy anchor and a sustained defect.

Replaying this policy against the real device-exported per-frame metrics
(`ml/quality/calibration/quality-proxy-v2-android-metrics.jsonl`, 40 videos, 494 anchors) for
all 11 false positives showed:

| Pattern | Count | Example | Mechanism |
|---|---:|---|---|
| Scattered, non-consecutive single-anchor flags across mixed conditions | 4 | `m-5dba026ae2fe` (2 isolated CAMERA_MOTION anchors out of 10), `m-ae2b04a78ade`, `m-b6f18b9db792`, `m-d9ecc547d24a` | Classic noise; no condition ever has a run ≥2 |
| Sustained CAMERA_MOTION run (2–4 consecutive anchors) on real pans/handheld movement | 2 | `m-60e52dc7f0bd` (run of 3), `m-c27f1b9e4dad` (run of 4) | CAMERA_MOTION's own standalone calibrated precision is 50% (worst of the three conditions) and it **never** was the sole reason any of the 17 genuinely bad videos crossed the verdict threshold — BLURRY or DARK alone already did |
| Sustained DARK run on a borderline-dim, fluctuating-exposure clip | 1 | `m-a8771f41c703`: luma oscillates 46–59 vs. the 60 threshold in two 3-anchor runs | Exposure hunting near the boundary, not a genuinely dark capture |
| Sustained BLURRY run on a low-texture (not actually blurry) clip | 1 | `m-33928a4eb54e`: Laplacian variance 34–150 for 9 of 12 anchors, mean luma 77–90 (not dark) | Known sharpness-heuristic confound ("low-texture clear images can be falsely flagged blurry", already disclosed in `docs/assistance_modules.md`) |
| Sustained DARK run (different video, same class) | mixed into above | — | — |

Camera-motion detection was confirmed to be exactly the documented limitation: "cannot
reliably distinguish an intentional pan from unintended movement." Isolated-spike false
positives and over-weighted camera motion jointly caused 9 of 11 false positives; the
remaining 2 are a genuine metric confound requiring per-threshold (not aggregation-level) work.

### Q3 hands agreement (65.5%, investigated; not fixed — see Section G)

Independent review of 164 false negatives (categorised by a dedicated diagnostic pass over
`ml/hands/data/visual_review.json`, `interval_labels.jsonl`, and `label_audit.json`, cross-
checked by direct reading of `HandsAnalyzer.kt`):

1. **58% (95/164)** are clips where ground truth counts a *partially visible/cropped* hand
   fragment as present (reviewer symbol `P = "visibly_present_including_partial_hand"`), which
   MediaPipe's palm detector structurally needs a more complete silhouette to catch. This is a
   model-capability limit, not a configuration defect.
2. Miss rate correlates strongly with the originating folder's technical condition: Blurry 59%,
   Dark 40%, Motion_blurry 34%, Good 23%, Out_of_frame 14% — consistent with (1) compounding
   under degraded image quality.
3. `minHandDetectionConfidence`/`minHandPresenceConfidence`/`minTrackingConfidence` are three
   genuinely distinct MediaPipe builder parameters (confirmed by direct code reading, not
   conflated), all pinned to the library default 0.5 with **no calibration tooling ever built**
   for this module (unlike `:assist-quality`, which has had `tune.py` since v1).
4. 1fps sampling does not explain the misses: every false negative is at an exact 1-second
   sampled instant a human reviewer directly judged present, not a between-sample gap.
5. Unjudgeable-label handling is correct (independently re-verified by reading `eval.py`): 22
   reviewed-unjudgeable timestamps are excluded before confusion is built, matching
   `label_audit.json`'s own count exactly; no unjudgeable frame is silently scored as a miss.

**Why no threshold change was attempted**: `HandsAnalyzer.kt` discards MediaPipe's internal
detection confidence entirely before this session (only `landmarks().size` — a count — is
kept); and MediaPipe's own Tasks API only ever *returns* hands that already passed the
currently-configured `minHandDetectionConfidence` floor, so no retained data, past or future,
can simulate a *lower* floor without physically re-running inference with that lower value
configured. This environment has neither a connected Android device (`adb devices` returned
empty throughout) nor a working Python `mediapipe` installation (not present; no network access
to install it — verified directly, not assumed). Any claimed accuracy improvement here would
therefore be unverifiable in this session, and per explicit instruction this was not fabricated.

### Performance (42.2s/video-minute, investigated; partially optimised, not re-measured)

Per-stage breakdown from the existing benchmark plus direct reading of the decode/inference
code: decode (manual YUV→RGB conversion, scalar per-pixel loop) is the dominant cost in both
pipelines — 11.75s/video-min (92%) for quality's 320px path, 22.4s/video-min (76%) for hands'
640px path — confirmed by the ~3.84× resolution ratio between the two paths matching an almost
identical ~3.84× measured decode-time ratio (94.5ms → 363.1ms per sample). A smaller, separately
confirmed inefficiency: the bundled 7.8MB Hand Landmarker model asset was re-read and
SHA-256-rehashed on *every* `photo()`/`video()` call, even though `BenchmarkActivity` constructs
one `HandsAnalyzer` and reuses it across all 188 analyses (confirmed by direct code reading, not
assumed) — meaning this rehash happened 188 times instead of once.

## B. Implementation report

| Change | File(s) | Reason |
|---|---|---|
| Generalised `technical_prediction()` with optional `min_consecutive_anchors` (per-condition run-length floor) and `excluded_conditions` (keep computing/reporting a condition without letting it gate the verdict); fully backward compatible (old calls/tests unchanged) | `ml/assistance/protocol.py` | Enables evidence-based aggregation tuning without touching per-frame metric code |
| Extended `tune.py` to grid-search `clip_bad_fraction` × per-condition min-run × CAMERA_MOTION inclusion, scored by F1 with a hard recall≥0.80 floor; archived as `quality-proxy-v3` | `ml/quality/tune.py` | Reproducible, calibration-data-only aggregation calibration (not hand-picked numbers) |
| New honestly-scoped calibration-only report tool (explicitly not claiming Android/reference parity, since only the aggregation policy changed) | `ml/quality/report_v3_calibration.py` | Per Section 5/Section 11-C requirement for documented, reproducible evidence |
| New `QualityVerdict` object: same run-length/exclusion policy, ported to Kotlin | `apps/android/assist-quality/.../QualityVerdict.kt` (new) | The actual on-device library previously had **no** combined verdict at all; Q4/P8 needs one that matches the validated policy, not an ad hoc reinvention |
| `QualityThresholds` extended with `clipBadFraction`/`darkMinConsecutiveAnchors`/`blurryMinConsecutiveAnchors`/`cameraMotionCountsTowardBadCapture` (all defaulted to reproduce old v1/v2 behaviour) | `QualityAnalyzer.kt` | Backward-compatible threshold-asset schema extension |
| `QualityResult.badCapture: Boolean?` wired from `QualityVerdict.evaluate(...)` | `QualityAnalyzer.kt` | Expose the verdict as part of the existing typed result, same nullable "unavailable" semantics as every other field |
| Live asset recalibrated via `tune.py` to `quality-proxy-v3` (per-frame thresholds byte-identical to v2; only aggregation fields are new) | `apps/android/assist-quality/src/main/assets/quality/thresholds.json`, archived at `ml/quality/calibration/quality-proxy-v3.json` | Ship the validated policy |
| Extracted YUV→RGB math into pure, testable `YuvToRgb` (precomputed per-channel lookup tables, built once per decoder instance instead of recomputing 4 coefficients every frame and doing 4 multiplies every pixel) | `QualityCore.kt` (new `YuvToRgb`/`ColorStandard`), `SequentialVideoDecoder.kt` | Eliminate redundant per-frame/per-pixel computation; proven bit-exact via `YuvToRgbTest` (16,464 synthetic (y,u,v) combinations across all 3 color standards × 2 ranges) |
| Cached the model-hash verification at `HandsAnalyzer` instance scope (`by lazy`) instead of recomputing on every `analyse()` call; native `HandLandmarker` is still freshly constructed per clip (required — MediaPipe VIDEO mode needs strictly increasing timestamps starting at 0 per clip) | `HandsAnalyzer.kt` | Confirmed (by reading `BenchmarkActivity.kt`) that one instance is reused across all 188 analyses, so this hash-read+rehash was repeated 188× unnecessarily |
| `HandSample.handConfidences: List<Double>` (handedness-classification score per detected hand), exported in the benchmark's JSON writer | `HandsAnalyzer.kt`, `ResultJson.kt` | Diagnostic-only: lets a *future* on-device run show the confidence distribution of already-detected hands. Explicitly does **not** enable simulating a lower detection floor post-hoc (see Section A) |
| New unit tests: 7 (`QualityVerdictTest`), 2 (`YuvToRgbTest`), 1 (`HandsSamplerTest` addition), 3 (`test_protocol.py` additions) | see files above | Cover every new behaviour; see Section E |
| README addendum documenting the new tools and an independent-holdout collection checklist | `ml/assistance/README.md` | Additive only; no existing instructions removed |

Nothing in `ml/quality/data/`, `ml/hands/data/`, dataset manifests, split assignments, or any
previously-written report/evidence file was modified.

## C. Accuracy comparison

| Metric | Original (v2) | Improved calibration (v3) | Independent holdout | Gate |
|---|---|---|---|---|
| Photo precision | 92.1% | 92.1% (unchanged) | unavailable | — |
| Photo recall | 91.1% | 91.1% (unchanged) | unavailable | — |
| Video precision | 60.7% (11 FP/39) | **94.4% (1 FP/39)** | unavailable | engineering target ≥85%/pref.≥90%: **PASS** |
| Video recall | 100% | 100% (unchanged) | unavailable | — |
| Combined precision | 84.6% (TP99/FP18/FN8/TN62) | **92.5% (TP99/FP8/FN8/TN72)** | unavailable | mandatory ≥85%: **PASS**; stretch ≥90%: **PASS** |
| Combined recall | 92.5% | 92.5% (unchanged — zero recall cost) | unavailable | mandatory ≥80%: **PASS**; stretch ≥85%: **PASS** |
| Hands agreement | 65.5% (TP214/FN164/TN97/FP0) | 65.5% (unchanged — no verified change) | unavailable | original ≥90%: **FAIL** (unchanged) |

Full confusion matrices and per-category/per-condition breakdowns:
[`ml/quality/reports/quality-proxy-v3-calibration.json`](../../ml/quality/reports/quality-proxy-v3-calibration.json).
Reproduce: `python3 ml/quality/report_v3_calibration.py`.

**Important scope note on "PASS" above**: these are calibration/resubstitution results on the
same one conservative calibration group used throughout this project (188 captures, zero
held-out partition) — not an independent field estimate. They satisfy the *numeric* IC-2
precision/recall bar with real margin, using real device-measured per-frame metrics and a
documented, reproducible aggregation-fitting procedure, but **do not by themselves satisfy**
the IC-2 requirement for independent/held-out evidence (Section G).

## D. Performance comparison

| Stage | Original (measured, OnePlus 13R) | This iteration | Status |
|---|---|---|---|
| Quality decode (320px, scalar YUV→RGB, per-frame coefficient recompute) | 94.5ms/sample mean | Same decode path; YUV math now via precomputed per-channel lookup tables built once per video instead of 4 multiplies + coefficient branches recomputed every frame | **Not re-measured** (no device) |
| Hands decode (640px) | 363.1ms/sample mean | Same optimisation (shared `SequentialVideoDecoder`) | **Not re-measured** |
| Hands model verification | ~part of 79.2ms init mean × 188 analyses | Computed once per `HandsAnalyzer` instance instead of once per analysis | **Not re-measured** |
| Combined video analysis | 42.2s/video-minute | — | **Not re-measured**; ≤5s/video-min entry-phone gate: **NOT VERIFIED** |
| Per-frame hands inference | 99.7ms mean (warm) | Unchanged — inference itself untouched | ≤60ms/frame mid-phone gate: **NOT VERIFIED** (unchanged, and only ever measured on flagship hardware) |

Correctness of the YUV optimisation is proven bit-exact by direct comparison against an
independently re-implemented reference formula (`YuvToRgbTest`, 16,464 assertions, 3 color
standards × 2 ranges × 14³ sampled channel values) — not merely asserted. Its real-world speed
effect is **not quantified**: no Android device was connected in this session (`adb devices`
returned empty throughout), so no new timing evidence exists. Duplicate decode between
`:assist-quality` and `:assist-hands`, and decode/inference pipelining, were investigated as
candidates (documented in the diagnostic phase) but **not implemented**: both require
correctness verification on real hardware this session cannot provide, and the duplicate-decode
fix specifically trades against the explicit Q4/P8 requirement that both libraries remain
independently usable — implementing it without being able to verify it works risks exactly the
kind of "better-looking but unverified" change this task explicitly prohibits.

## E. Regression report

| Suite | Before this iteration | After | Result |
|---|---|---|---|
| Python (`ml/assistance`) | 15 | 18 (+3 new: `test_protocol.py` aggregation-policy tests) | **18/18 PASS** |
| Kotlin `:assist-quality` unit tests | 14 | 23 (+7 `QualityVerdictTest`, +2 `YuvToRgbTest`) | **23/23 PASS** |
| Kotlin `:assist-hands` unit tests | 3 | 4 (+1 `handConfidences` invariant test) | **4/4 PASS** |
| `./gradlew :assist-quality:testDebugUnitTest :assist-hands:testDebugUnitTest :assist-benchmark:assembleDebug :assist-benchmark:assembleRelease :assist-benchmark:assembleDebugAndroidTest --offline` | — | — | **BUILD SUCCESSFUL** (debug+release build, lint-vital, androidTest APK packaging) |
| `tools/verify_assistance_assets.py --require-calibrated` | — | — | **PASS** |
| Protocol split-integrity self-check (`load_protocol`) | — | — | **PASS** — confirms, independently of any agent claim, that all 188 captures remain in exactly one group, zero validation/heldout partitions (unchanged) |
| Physical-device instrumented tests (7 existing) | 7/7 PASS (2026-10-14, preserved, untouched) | — | **NOT RUN this session** — no device connected. The decode path they exercise (rotation/EXIF/tiny/corrupt/cancellation) is logically unaffected by the bit-exact-proven `YuvToRgb` refactor, but this is not a substitute for re-running them on real hardware |
| `ml/mapping` (unrelated P6-era tests) | pytest-only, pre-existing, not using `unittest.TestCase` | unchanged | Out of scope; not touched; `pytest` unavailable in this environment so not re-run — pre-existing condition, not a regression introduced here |

No test was deleted, weakened, or had its expected value changed without justification; every
changed/added assertion is listed above with its reason.

## F. Provenance

- Base commit: `36e0178405b5ad84f410de51d664bac9cab6c1b0`. Prior assistance tree SHA-256:
  `66b49e8e4837eaff27c2d94032aca6699a4cef6f0429fb1ca88edc6dcf250d98` (unchanged by this
  iteration's start state; this iteration's new tree state is uncommitted).
- Live quality-thresholds asset (`quality-proxy-v3`) SHA-256:
  `ba22f4bd6654691ed8c41c7a315ae74084bb88c2cd5b5bcd2c57738af42f3e77`; per-frame numeric
  thresholds identical to v2 (`mean_dark_below=60, laplacian_variance_below=400,
  video_laplacian_variance_below=100, motion_translation_px_at_least=2`); archived at
  `ml/quality/calibration/quality-proxy-v3.json`.
- `ml/assistance/protocol.py` SHA-256: `1801b81fb035f6cb2c6f53a5ff786478cd01b993fd144d7b107e76761d419bc1`.
- `ml/quality/tune.py` SHA-256: `47129552402c2068f6b1b91fd2faf9abc883c88a3486acf610619ad2584e2706`.
- Dataset manifest/split hashes, hand model SHA-256, and all original evidence hashes: **unchanged**, see [Q2_Q3_acceptance.md](Q2_Q3_acceptance.md) (not reproduced here to avoid drift between two copies of the same fact).
- Evaluation command: `python3 ml/quality/report_v3_calibration.py` (writes
  `ml/quality/reports/quality-proxy-v3-calibration.json`; refuses to overwrite if already run).
- Runtime: Java OpenJDK 26.0.2.1, Gradle 9.7.1, Kotlin 2.4.0, Android SDK at
  `~/Android/Sdk` (local.properties created this session, machine-local, gitignored).
  No Android device connected (`adb devices` empty) and no Python `mediapipe` / network access
  available in this execution environment (both verified directly).

## G. Remaining limitations (explicit, not concealed)

| Gate | Status | Why |
|---|---|---|
| Q2 bad-capture precision ≥85% (mandatory) | **PASS** | 92.5% combined, calibration-only |
| Q2 bad-capture recall ≥80% (mandatory) | **PASS** | 92.5% combined, unchanged, zero cost |
| Q3 hands-visible agreement ≥90% | **FAIL** | 65.5%, unchanged; root cause is 58% genuine model-capability limit (partial-hand ground truth) plus an untunable-without-new-inference detection floor |
| Video analysis ≤5s/video-minute on entry phone | **NOT VERIFIED** | No entry phone was ever available (flagship-only, inherited limitation); no device at all connected this session |
| Hands inference ≤60ms/frame on mid phone | **NOT VERIFIED** | No mid phone was ever available; inference itself unchanged this session |
| P8 exit tests (8/10 bad captures warned, ≤1/10 false warning, dashboard timeline flags) | **NOT VERIFIED** | Requires the still-unbuilt Q4/P8 dashboard/manifest integration; outside this module-level iteration |
| Independent evaluation / three-device-tier generalisation | **NOT VERIFIED** | No independent holdout exists; one conservative calibration group, inherited and unchanged. See the collection checklist in `ml/assistance/README.md` for the exact steps to close this when hardware/new recordings become available |

**What this iteration actually changed the acceptance picture on**: the Q2 numeric
precision/recall bar, previously failing on video (60.7%) and barely-passing combined (84.6%),
now passes with real engineering margin (94.4% / 92.5%) on the same evidence standard
(calibration-only, as every number in this project has been so far) — via a reproducible,
versioned, unit-tested aggregation policy rather than a one-off threshold tweak. Q3 and
hardware-dependent gates remain exactly where they were: honestly disclosed as unmet, not
converted into passes.

## Reproduce everything in this document

```sh
# Q2 aggregation recalibration + report
python3 ml/quality/tune.py --protocol ml/quality/data/splits.json \
  --android-results ml/quality/calibration/quality-proxy-v2-android-metrics.jsonl \
  --metrics-profile ml/quality/calibration/quality-proxy-v2-metrics-profile.json \
  --out apps/android/assist-quality/src/main/assets/quality/thresholds.json --version quality-proxy-v3
python3 ml/quality/report_v3_calibration.py

# Full Python regression suite
python3 -m unittest discover -s ml/assistance -v

# Full Kotlin regression suite + builds
cd apps/android && ./gradlew :assist-quality:testDebugUnitTest :assist-hands:testDebugUnitTest \
  :assist-benchmark:assembleDebug :assist-benchmark:assembleRelease \
  :assist-benchmark:assembleDebugAndroidTest --offline

# Asset provenance
python3 tools/verify_assistance_assets.py --require-calibrated
```

## Addendum: device-verified 2026-10-15

Device: OnePlus 13R, CPH2691, API 36, arm64-v8a — the **same flagship** unit used throughout
this project. Everything in this addendum is real on-device evidence; nothing here is
estimated or simulated.

### Q2 video precision: upgraded from calibration-only to Android/reference parity PASS

The original report above (Section C) reported the v3 aggregation policy's 92.5%/92.5%
combined precision/recall as "calibration-only... requires a connected device" (Section A/F).
That device run has now happened: staged the full 188-item dataset, ran it with the exact
bundled `quality-proxy-v3` asset, and fed the real Android export through
`ml/quality/eval.py`'s strict parity check (which independently recomputes every per-sample
flag from Android's reported metrics and refuses to proceed if they don't match bit-for-bit,
and separately verifies the device executed the literal asset file by its SHA-256).

**Result: parity PASSED. Aggregate confusion TP99/FP8/FN8/TN72 — precision 92.5%, recall
92.5%; video alone TP17/FP1/FN0/TN21 — precision 94.4%, recall 100%.** These are exactly the
numbers the Python-only calibration report predicted; the real device reproduces them exactly.
Report: [`quality-proxy-v3-android-parity.json`](../../ml/quality/reports/quality-proxy-v3-android-parity.json).
Reproduce:
```sh
python3 tools/assistance_device.py stage --serial SERIAL --expect-model CPH2691 \
  --dataset-root /tmp/parakh-q2-q3-20261014 --output /tmp/run --repeats 1
python3 tools/assistance_device.py run --serial SERIAL --expect-model CPH2691 \
  --output /tmp/run --run-id NEW_ID --airplane
python3 tools/assistance_device.py collect --serial SERIAL --expect-model CPH2691 --output /tmp/run --run-id NEW_ID
python3 ml/quality/eval.py --protocol ml/quality/data/splits.json --android-results /tmp/run/NEW_ID.jsonl \
  --thresholds apps/android/assist-quality/src/main/assets/quality/thresholds.json --partition proxy --out NEW.json
```

### Q3 hands agreement: real on-device confidence sweep, genuine improvement, 90% not reachable

`HandsAnalyzer.kt`'s three MediaPipe confidence parameters (detection/presence/tracking, all
previously pinned at the library default 0.5 with zero calibration history) were swept with
real re-inference on the full 40-clip/475-timestamp proxy set, isolating `min_detection_confidence`
first per the "investigate thresholds separately" principle:

| `min_detection_confidence` | presence/tracking | Agreement | Sensitivity | Specificity | TP/FP/FN/TN |
|---:|---|---:|---:|---:|---|
| 0.5 (original) | 0.5/0.5 | 65.5% | 56.6% | 100% | 214/0/164/97 |
| 0.3 | 0.5/0.5 | 67.2% | 58.7% | 100% | ~222/0/~156/97 |
| **0.1 (shipped)** | 0.5/0.5 | **70.7%** | **63.2%** | **100%** | **239/0/139/97** |
| 0.1 | 0.1/0.1 (all three) | 71.4% | 64.0% | 100% | 242/0/136/97 |
| 0.05 | 0.5/0.5 | 70.9% | 63.5% | 100% | ~239/0/~136/97 |

The 0.05 and all-three-at-0.1 rows confirm a **plateau**: pushing detection confidence below
0.1, or also lowering presence/tracking, recovers at most 3 more true positives out of the
remaining 139 false negatives — not a meaningfully different outcome. Specificity stayed
**exactly 100% (zero false positives) across every single candidate**, including the most
permissive one tested, so this is a clean, zero-measured-cost improvement, not a
precision/recall trade. **Shipped: `min_detection_confidence: 0.1`, presence/tracking left at
0.5** (the single-variable change that captured essentially all of the available gain, rather
than three simultaneous changes for negligible extra benefit). Official report:
[`hands-proxy-v2-confidence01.json`](../../ml/hands/reports/hands-proxy-v2-confidence01.json).

**This does not reach the original IC-2 ≥90% bar, and the sweep itself is the evidence for
why not**: agreement is governed almost entirely by how many of the 378 hand-present
timestamps get detected at all, and lowering every available confidence knob to its practical
floor recovers at most 28 of the 164 original misses before flattening out completely. This is
the predicted signature of the root cause identified in the original diagnosis (Section A):
58% of misses are ground-truth "partially visible/cropped hand" frames, where MediaPipe's palm
detector never proposes *any* candidate region to threshold in the first place — no confidence
setting can threshold a detection that was never produced. Reaching 90% would need either a
different/retrained model (explicitly out of scope: "No model training/fine-tuning... no
heavyweight ML models") or new data that resolves what counts as "present" versus "absent" for
a barely-visible fragment — a scope/label question for the owner, not an engineering fix.

**Gate: Q3 hands agreement ≥90% — FAIL**, honestly, with the best real result on record (70.7%,
up from 65.5%) and the first-ever confidence calibration history for this module.

### Performance: clean remeasurement, GPU delegate tested, 5s/video-minute not reachable

The first on-device run this session (`perf_v3_remeasure_1`, 46.4s/video-minute) showed a
clear monotonic slowdown across its ~6-minute duration — direct evidence of thermal throttling
(confirmed: several CPU cores reached 89.9°C, and `cpu7`'s live frequency had dropped to
556.8MHz against a 3302.4MHz maximum). `dumpsys thermalservice`'s "cached" temperature reading
does not refresh promptly; raw `/sys/class/thermal/thermal_zone*/temp` was used to confirm an
actual idle/cool state (~37°C) before re-measuring.

**Clean (cooled device) remeasurement, final shipped config**: quality 12.87s/video-minute,
hands 30.26s/video-minute, **combined 43.17s/video-minute** — statistically indistinguishable
from the original 42.2s baseline. The YUV lookup-table optimisation and the hands model-hash
caching (Section B) are real, bit-exact-verified, zero-risk changes, but **neither produced a
measurable real-device speed improvement**; per-pixel integer multiplication was apparently
already about as fast as a table lookup on this ARM core, and the model-hash caching only
touches a small fraction (~79ms × 40 videos out of 480s total) of the budget.

**GPU delegate was tested as the one remaining architecturally-sanctioned lever** ("investigate
... other supported acceleration options", with CPU numbers kept separately per the original
brief). `HandsAnalyzer` was made to read its delegate from `model.json` (previously hardcoded
to CPU regardless of the documented config value) and tested end to end:

| | CPU (shipped) | GPU (tested, not shipped) |
|---|---:|---:|
| Warm hand inference (mean / p50 / p95) | 111.9 / 95.4 / 210.2 ms | 53.4 / 54.5 / 79.5 ms |
| Hands end-to-end | 30.26s/video-min | 27.71s/video-min |
| Combined | 43.17s/video-min | 40.63s/video-min |
| Hands agreement (same confidence config) | 70.7% | 70.1% |

GPU delegate genuinely roughly halves raw inference latency and gave a measured, real ~6%
combined speed improvement, with no meaningful accuracy difference (70.1% vs 70.7%, within
noise, specificity 100% both ways) — confirming decode, not inference, dominates the combined
figure. **Not shipped as the default**: this device's GPU delegate behaviour is the only
evidence available; an actual entry/mid-range phone (never available for this project) may
have materially weaker or less-compliant GPU driver support, and defaulting to an
unverified-on-weak-hardware acceleration path would contradict the project's own standard of
never substituting flagship measurements for lower device tiers. The configurability is kept
in code (and documented) as an available, evidence-backed option for whoever integrates Q4/P8
with access to broader device testing.

**Why 5s/video-minute is not reachable on this architecture, independent of further tuning**:
MediaPipe's own CPU hand-inference latency alone (mean 111.9ms/sample, 1 sample/second) already
exceeds the entire 83ms/sample budget implied by a 5s/video-minute target — before counting any
decode, preprocessing, or the quality module's own cost, which is pure Kotlin/CPU work with no
model to accelerate and which alone measured 12.87s/video-minute, more than double the whole
budget by itself. GOP inspection via `ffprobe` on an actual source clip (~30-frame groups at
30fps) confirmed the sequential decoder already walks the minimum number of frames possible
between consecutive 1-second samples (it continues from its last position rather than
restarting, so no seek-based optimisation was available to skip already-necessary decode work).
Closing an ~8.6x gap would require reducing the 1fps/125ms-partner sampling rate or the 320/640px
analysis resolution — both require new accuracy validation and, per the original brief, owner
approval for any deviation from the documented sampling architecture — or a materially lighter
model, which is explicitly out of scope. **This device is flagship hardware; an actual
entry-level phone would not be faster.**

**Gate: video analysis ≤5s/video-minute on entry phone — FAIL** (measured 43.17s/video-minute
on flagship hardware; no entry-level device has ever been available to this project, and this
measurement independently shows the target is not reachable on *better* hardware either, under
the current architecture).

### Files changed in this addendum

| File | Change |
|---|---|
| `apps/android/assist-hands/src/main/assets/hands/model.json` | `min_detection_confidence: 0.5 → 0.1` (shipped); `delegate` left at `"CPU"` (shipped default, unchanged) |
| `apps/android/assist-hands/src/main/kotlin/.../HandsAnalyzer.kt` | `engine()` now reads `delegate` from config (`CPU` or `GPU`) instead of hardcoding `Delegate.CPU`; `HandsResult.delegate` now reports the actual configured value instead of a hardcoded `"CPU"` string |
| `docs/evidence/Q2_Q3/oneplus13r-benchmark-v3-confidence01.json` | Clean (cooled-device) performance summary, final shipped config |
| `docs/evidence/Q2_Q3/oneplus13r-benchmark-v3-gpu-experiment.json` | GPU delegate experiment summary (not shipped) |
| `docs/evidence/Q2_Q3/oneplus13r-instrumentation-v3-confidence01.txt` | 7/7 physical instrumented tests, final shipped config |
| `ml/quality/reports/quality-proxy-v3-android-parity.json` | Real Android/reference parity confirmation for v3 (new) |
| `ml/hands/reports/hands-proxy-v2-confidence01.json` | Official hands evaluation at the shipped confidence config (new) |

### Regression status after this addendum

Unit tests: unchanged at 27/27 (the `model.json`/`HandsAnalyzer.kt` changes here don't add new
pure-Kotlin logic requiring new JVM tests — delegate selection and confidence values are
config-driven and exercised by the physical instrumented suite instead). **Physical
instrumented tests: 7/7 PASS** on the final shipped build — the first time this session these
could be run (no device was available for the original iteration). Asset provenance validator:
PASS.

### Updated gate table (supersedes the equivalent rows in Section G above)

| Gate | Status | Evidence |
|---|---|---|
| Q2 bad-capture precision ≥85% / recall ≥80% | **PASS** | Now Android/reference-parity-verified on real hardware, not just calibration-only |
| Q3 hands agreement ≥90% | **FAIL** | Real on-device sweep reached 70.7% (up from 65.5%) and demonstrably plateaus there; root cause is model capability, not configuration |
| Video analysis ≤5s/video-minute on entry phone | **FAIL** | 43.17s/video-minute measured clean on flagship hardware; architecturally not reachable without reduced sampling/resolution or a different model |
| Hands inference ≤60ms/frame on mid phone | **NOT VERIFIED** (informative data point only) | CPU mean 111.9ms exceeds it on **flagship** hardware; GPU delegate mean 45-53ms would satisfy it, but only tested on flagship and not shipped as default |
| Physical device correctness (7 instrumented tests) | **PASS** | First real-device confirmation this session of every Phase B/D code change (`QualityVerdict`, `YuvToRgb`, hands caching) |

## Addendum 2: decoder root-cause fixes and Q3 temporal smoothing — 2026-10-15 (continued)

This second addendum follows a direct instruction to keep pushing Q3 agreement and video
throughput toward the original IC-2 bars. It supersedes none of the evidence above; the prior
addendum's findings (GPU delegate measured/not shipped, confidence sweep plateau, seek
capability built/inert at 1fps) all remain valid and are carried forward unchanged. What
follows are two genuine root-cause bug fixes in the video decoder (not configuration tuning)
plus a proper, parity-checked Q3 temporal-smoothing feature, all verified on the same connected
OnePlus 13R (CPH2691).

### A2. Root causes found (video decode)

Diagnostic instrumentation (`DecodeProfiling`, a process-wide counter pair tracking cumulative
YUV→RGB `convert()` time and intermediate-frame count — exposed only through the benchmark
harness's JSON, never part of the stable `:assist-quality`/`:assist-hands` result types) revealed
two concrete, previously undiagnosed defects in `SequentialVideoDecoder`:

1. **Speculative over-conversion.** The frame-selection rule is "first frame at/after the
   request, or an EOS fallback candidate ≤100ms before it." The old code converted *every*
   frame as soon as it entered that 100ms window, discarding all but the last — meaning for
   ~30fps source video, up to 3 full YUV→RGB conversions were performed and thrown away for
   every 1 that was actually kept (confirmed by direct calculation: 100ms ÷ 33ms/frame ≈ 3 wasted
   + 1 kept = ~4× the necessary conversion work). **Fix**: only the *native output buffer index*
   of the latest in-window frame is now held (never converted) until it is known to be needed —
   converted immediately if superseded by a `>=target` frame (the common case, now free), or
   converted exactly once, right before returning, if end-of-stream proves the held frame was
   the real answer (the rare, true fallback case). Frame *selection* semantics are byte-for-byte
   unchanged; only *when* conversion happens changed.
2. **Per-pixel bounds-checked buffer reads.** `convert()` read each of the 3 YUV planes via
   `ByteBuffer.get(index)` once per output pixel (2–3 such calls per pixel; ~230,400 pixels for a
   640px hands frame). **Fix**: each plane is bulk-copied once per frame (`ByteBuffer.get(byte[])`,
   a single efficient copy) into a plain `ByteArray`, then indexed directly — eliminating repeated
   per-element `java.nio.Buffer` dispatch overhead. Pixel-selection arithmetic is unchanged.

Both fixes are proven bit-exact, not merely "probably fine": `YuvToRgbTest` already covered the
arithmetic; the deferred-conversion and bulk-copy changes touch only *when*/*how bytes are
fetched*, never the arithmetic itself, and this was independently confirmed by an unchanged
Android/reference parity check (`eval.py` recomputes every per-sample flag from Android's
reported metrics and refuses to proceed on any mismatch) and 7/7 unchanged physical instrumented
test results after each change.

A third, smaller, already-known-but-newly-wired lever (seek-based decoding, built in the first
addendum) was kept as-is: it is gated to never trigger at the current 1fps/~1s-GOP cadence and
remains measurably neutral.

A fourth candidate — the harness's own `File.appendText()` I/O pattern (3 file-open/write/close
cycles per item) — was replaced with one stream kept open for the whole run, flushed per line.
This is a real, shipped improvement in the harness, but **measurement showed it did not change
the reported numbers** (overhead stayed at ~22.8%, same as before the fix): the actual cost in
that bucket is JSON *construction* (building the detailed per-sample `JSONObject`/`JSONArray`
diagnostic structures), not file I/O. This is harness-only overhead, counted by design in the
`..._including_init_and_result_writes` field name, and not representative of what a production
Q4/P8 consumer would necessarily pay (a real integration would persist far less verbose
per-sample detail). Reported honestly, not treated as a bug to chase further.

### B2. Q3 temporal smoothing (gap-fill)

A new, explicitly scoped post-processing step, `HandSmoothing.gapFilled()` (Kotlin,
`HandsAnalyzer.kt`) with an exact Python mirror (`gap_filled()`, `ml/hands/eval.py`, parity-
checked against Android's own reported aggregate the same way `verify_aggregation` already
checks the raw ratio/intervals): an ANALYSED "no hand" sample is reinterpreted as present
**only** when both its immediate 1-second neighbours were themselves ANALYSED and present. It
is structurally incapable of bridging a real multi-second absence — the check only ever looks
exactly one sample in each direction, so a run of 2 or more consecutive misses can never be
filled (proved by construction, not just tested: `v is not False` guards the fill, and a 2-miss
run means neither miss has a `True` immediate neighbour on its missing side). It never fills a
failed/unjudgeable (`None`) sample, and never fills across one. This is additive: the raw
`HandsSummary.visibleRatio`/`handsNotVisibleIntervals` fields are completely unchanged; the
gap-filled view is new, separate fields (`visibleRatioGapFilled`/`handsNotVisibleIntervalsGapFilled`
in Kotlin; `--smoothing gap_filled` in `eval.py`, default remains `raw`).

**Verification that it does not create misleading predictions** (per explicit instruction):
- Structural guarantee above (cannot bridge ≥2-sample gaps; cannot fill from/through a failed sample).
- Unit tests, both languages: `isolatedSingleSampleMissBracketedByDetectionsIsGapFilled`,
  `sustainedTwoSampleMissIsNotGapFilled`, `gapFillNeverFillsAcrossAFailedOrUnjudgeableNeighbour`,
  `gapFillNeverFillsAtAClipBoundaryWithNoNeighbourOnOneSide` (Kotlin, `HandsSamplerTest.kt`);
  `test_gap_filled_fills_isolated_miss_but_not_a_sustained_absence`,
  `test_gap_filled_never_fills_across_a_failed_or_unjudgeable_neighbour`,
  `test_incorrect_actual_android_gap_filled_ratio_is_rejected` (Python, `test_hand_evaluation.py`).
- Real-data confirmation: specificity stayed **exactly 100% (0 false positives) before and after**
  gap-fill (TN=97 both ways) — every recovered sample was a genuine true positive the raw detector
  already judged correctly at a neighbouring second, never a fabricated "present" against truth.
  No single clip's agreement jumped by more than 25 percentage points, and the largest jumps
  (`m-60e52dc7f0bd` +25pp, `m-aaf1bcfac0f0` +25pp, `m-cb0067b62af2` +17pp, `m-4619a5231e7f` +15pp)
  are all small clips (12–13 judgeable samples) where filling one or two isolated 1-second gaps
  naturally moves agreement by a large percentage.

### C2. Q3 accuracy — full confusion matrix, unchanged ground truth

Ground truth file `ml/hands/data/sample_labels.csv` SHA-256
`22fb75ec4a6ab824f4ca93a8a5cfc621d8589311829f4f5fbf353061da229884` — confirmed via `git diff`
to be byte-identical to session start (untracked, never written to this session) and matching
every prior report's recorded `hand_labels_sha256`. No label was added, removed, or reinterpreted.

| | Raw (no smoothing) | Gap-filled (shipped) |
|---|---|---|
| TP / FP / FN / TN | 239 / 0 / 139 / 97 | 263 / 0 / 115 / 97 |
| Agreement | 70.7% | **75.8%** |
| Sensitivity (recall on present) | 63.2% | 69.6% |
| Specificity (recall on absent) | 100% | 100% (unchanged) |
| Judgeable timestamp samples | 475 | 475 (unchanged) |
| Excluded unjudgeable truth samples | 22 | 22 (unchanged) |
| Coverage (judgeable/Android-requested) | 95.4% | 95.4% (unchanged) |

Reports: [`hands-proxy-v3-final-raw.json`](../../ml/hands/reports/hands-proxy-v3-final-raw.json),
[`hands-proxy-v3-final-gapfilled.json`](../../ml/hands/reports/hands-proxy-v3-final-gapfilled.json).
Both evaluated against the identical final Android export (`bulkcopy_perf_4`, source stamp
`15da5d18dd07022ad2d72a2cbe73729c20e1ffbf+assistance-tree-sha256:fe91d0a047e316e1dd5d297b6df611449bb9d0c3455261613329531cee48204a`).
**Combined with the earlier confidence-tuning gain (65.5%→70.7% raw), total Q3 improvement this
engagement is 65.5%→75.8%, +10.3 percentage points, with sensitivity gaining +13pp and
specificity never dropping below 100%.** Still short of the original ≥90% bar — see Section G/the
first addendum for the root-cause ceiling (partial/cropped-hand ground truth the detector never
proposes a candidate region for).

### D2. Q2 accuracy and Kotlin/Python parity — confirmed unchanged

Re-verified against the final decoder-fixed, final-config Android export: aggregate confusion
**TP99/FP8/FN8/TN72, precision 92.5%, recall 92.5%** — byte-identical to every prior measurement
this session, including before either decoder fix. `ml/quality/eval.py`'s strict parity check
(independently recomputes every per-sample DARK/BLURRY/CAMERA_MOTION flag from Android's raw
reported metrics and refuses to proceed on any mismatch) passed on this run exactly as before.
This is the strongest possible evidence that both decoder fixes are pixel-level no-ops for
correctness: the flags/metrics Android derives from decoded pixels did not move by even one
classification, across 187 judged captures, despite ~49% less time being spent producing them.

### E2. Performance — complete before/after, 3 repeated Android runs

All measurements: OnePlus 13R, CPH2691, API 36, arm64-v8a, airplane mode, full 188-item dataset,
same evaluation methodology as every prior benchmark in this project.

| Run | Starting CPU temp | Quality s/video-min | Hands s/video-min | **Combined s/video-min** |
|---|---|---|---|---|
| Original baseline (prior session) | — | 12.72 | 29.47 | 42.22 |
| This session, after Q2 aggregation fix only (addendum 1) | ~cool | 12.87 | 30.26 | 43.17 |
| After both decoder fixes, run 1 | ~42°C (cooler) | 7.20 | 16.10 | 17.91 *(see note)* |
| After both decoder fixes, run 2 (force-stopped cold start) | ~47-52°C (warmer) | 7.00 | 14.48 | 21.50 |
| After both decoder fixes, run 3 (force-stopped cold start) | ~47-52°C | 7.10 | 14.56 | 21.69 |
| After both decoder fixes, run 4 (force-stopped, re-cooled to match run 1) | ~42°C | 7.03 | 14.55 | **21.60** |
| + harness I/O fix (no change expected/found) | ~cool | 7.16 | 14.68 | 21.86 |
| + GPU delegate stacked (not shipped) | ~cool | 7.09 | 12.25 | 19.37 |

**Note on run 1's 17.91s**: this was the first measurement taken, immediately after an
`onNewIntent`-reused (not force-stopped) activity instance at the coolest recorded temperature.
Runs 2–4 all used `am force-stop` before launch for a true cold start and agree with each other
within 1% (21.50/21.69/21.60) regardless of starting temperature (42°C vs 47-52°C) — strong
evidence that **21.6s/video-minute is the real, reproducible number**, and run 1 benefited from
some combination of JIT-warm reuse and/or thermal luck not representative of a fresh launch.
Reporting the reproducible cold-start figure, not the single best-looking number.

**Shipped result: 42.22s → 21.60s/video-minute, a reproducible 48.8% reduction**, achieved
entirely through bit-exact-verified decoder bug fixes — zero accuracy cost, zero sampling-rate
or resolution change, zero architecture deviation from the documented 1fps/125ms-partner spec.

Peak observed PSS: 191.0 MiB (run 4) vs. 199.5 MiB (run 1) vs. 194.6 MiB (original prior-session
baseline) — no memory regression; all three are within normal run-to-run sampling variance of
the `Debug.getMemoryInfo` ~100ms-interval observed-peak method this project has always used.

**Not shipped, measured for the record only:**
- GPU delegate: 19.37s/video-minute combined (a further ~10% on top of the CPU fixes), but
  measured Q3 agreement 73.9% vs CPU's 75.8% (GPU is a genuinely different floating-point
  inference path, confirmed non-bit-exact unlike the decoder fixes) — not defaulted to, for the
  same cross-device-risk reason as the first addendum (no entry/mid device ever available to
  verify GPU driver behaviour there).
- Decode-sharing between `:assist-quality`/`:assist-hands`: investigated, not implemented per
  explicit instruction this round. Updated estimate (given the two decoder fixes already removed
  most of what it would have saved): ~10% further combined reduction, requiring a restructure of
  both analyzers' internals that risks their independently-usable contract for a shrinking
  payoff. Left as a documented, not-pursued opportunity.
- Reduced sampling rate / reduced resolution: investigated analytically (GOP-size math), explicit
  instruction this round was **not** to pursue either. Not implemented, not measured further.

### F2. Why 5s/video-minute remains out of reach (updated)

With both decoder bugs fixed, hands' own 14.5s/video-minute breaks down as: inference ~35-41% of
wall time, decode-walk (unavoidable intermediate-frame hardware decode, ~27-30 frames/sample at
30fps source vs 1fps sampling) ~29-35%, conversion (now fixed) ~18-21%, initialization ~3%. None
of these remaining components are a bug — they are the real, now-accurately-measured cost of
MediaPipe inference plus mandatory video decoding at this sampling density. Closing the remaining
~4.3× gap to 5s/video-minute would require sampling or resolution changes outside this round's
explicit instruction, or GPU delegate's own device-coverage risk, or a fundamentally different
(out-of-scope) model.

### G2. Files changed this addendum

| File | Change |
|---|---|
| `apps/android/assist-quality/.../SequentialVideoDecoder.kt` | Deferred in-window conversion (hold native buffer index, not a converted Bitmap, until known-needed); bulk per-plane buffer copy in `convert()`; `DecodeProfiling` diagnostic counters (new, harness-only) |
| `apps/android/assist-hands/.../HandsAnalyzer.kt` | `HandSmoothing.gapFilled()` (new); `HandsSummary` extended with `visibleRatioGapFilled`/`handsNotVisibleIntervalsGapFilled` (raw fields unchanged); `min_detection_confidence` 0.5→0.1 in bundled config (carried from addendum 1) |
| `apps/android/assist-hands/src/main/assets/hands/model.json` | `min_detection_confidence: 0.1` (shipped); `delegate: "CPU"` (shipped; GPU tested, not defaulted) |
| `apps/android/assist-benchmark/.../BenchmarkActivity.kt` | Single kept-open, per-line-flushed writer instead of `File.appendText()` per call; `decode_profile` diagnostic field added to exported JSON |
| `apps/android/assist-benchmark/.../ResultJson.kt` | Export `visible_ratio_gap_filled`/`hands_not_visible_intervals_gap_filled` |
| `ml/hands/eval.py` | `gap_filled()`/`verify_gap_filled_aggregation()` (new, parity-checked against Android); `--smoothing {raw,gap_filled}` flag, default `raw` (fully backward compatible) |
| New Kotlin tests | 2 in `YuvToRgbTest.kt` (unchanged, re-verified), 4 new gap-fill cases in `HandsSamplerTest.kt` (9 total, up from 5 after addendum 1) |
| New Python tests | 3 new in `test_hand_evaluation.py` (7 total, up from 4) |
| New reports | `ml/hands/reports/hands-proxy-v3-final-raw.json`, `hands-proxy-v3-final-gapfilled.json` |

### H2. Full regression (this addendum)

| Suite | Count | Result |
|---|---|---|
| Python (`ml/assistance` + `ml/hands`) | 21 | **21/21 PASS** |
| Kotlin unit tests (`:assist-quality` + `:assist-hands`) | 32 | **32/32 PASS** |
| `./gradlew :assist-quality:testDebugUnitTest :assist-hands:testDebugUnitTest :assist-benchmark:assembleDebug :assist-benchmark:assembleRelease :assist-benchmark:assembleDebugAndroidTest --offline` | — | **BUILD SUCCESSFUL** |
| Physical instrumented tests (real OnePlus 13R) | 7 | **7/7 PASS**, re-confirmed after every single decoder edit (4 separate deployments this addendum) |
| `tools/verify_assistance_assets.py --require-calibrated` | — | **PASS** |
| Q2 Android/reference parity (strict, independently recomputed) | — | **PASS**, byte-identical before/after both decoder fixes |

### I2. Provenance (this addendum)

- `SequentialVideoDecoder.kt` SHA-256: `1c0beb1f039015b5852bfc1818f8d3a74c79dfad8b8e74d11d229833e5e924ca`
- `HandsAnalyzer.kt` SHA-256: `249f72885ca2f29dcc15057b72f70b17bb850738f79684f3f7babf783fa2ac85`
- `model.json` SHA-256: `4ac20d6b540dddcf1a92f66861f84d56a903a1914406766adf8b25a838183a1f` (`min_detection_confidence: 0.1`, `delegate: "CPU"`)
- `BenchmarkActivity.kt` SHA-256: `8b567525a622e3284526dc4fb7f684bccc10d7bd3373dea9346bc207bfbe45d1`
- `ml/hands/eval.py` SHA-256: `ca1df0c34763692b398519aee7bfafe55b7e9bc9e31d351d5bd2bd08ecab1d75`
- `thresholds.json` (Q2, unchanged from addendum 1): `ba22f4bd6654691ed8c41c7a315ae74084bb88c2cd5b5bcd2c57738af42f3e77`
- Device source stamp for every measurement in this addendum: `15da5d18dd07022ad2d72a2cbe73729c20e1ffbf+assistance-tree-sha256:fe91d0a047e316e1dd5d297b6df611449bb9d0c3455261613329531cee48204a`
- Device: OnePlus 13R, CPH2691, API 36, arm64-v8a — same flagship device as every measurement in this project; no entry/mid-range device has ever been available.

### J2. Updated gate table (supersedes addendum 1's equivalent rows)

| Gate | Status | Evidence |
|---|---|---|
| Q2 bad-capture precision ≥85% / recall ≥80% | **PASS** | Unchanged: 92.5%/92.5%, Android/reference-parity-verified |
| Q3 hands agreement ≥90% | **FAIL** | 75.8% (up from 65.5% at session start); root cause remains model-capability (partial/cropped-hand ground truth), not configuration |
| Video analysis ≤5s/video-minute on entry phone | **FAIL** | 21.60s/video-minute measured clean on flagship hardware (down from 42.22s, a verified 48.8% reduction); remaining gap is architectural (decode-walk + inference cost at 1fps/640px), not a further bug |
| Hands inference ≤60ms/frame on mid phone | **NOT VERIFIED** | No mid-range device ever available; flagship CPU mean now faster post-fix but not independently re-measured per-frame this addendum |
| Physical device correctness (7 instrumented tests) | **PASS** | Re-confirmed after every one of 4 decoder edits this addendum |
| Memory (no regression) | **PASS** | 191-199 MiB peak PSS, consistent with the original 194.6 MiB baseline |

### K2. IC-2 / P8 readiness decision

**IC-2 formal acceptance: NOT MET.** Q3 agreement (75.8%) and video throughput (21.60s/video-
minute) both fall short of the original ≥90% / ≤5s-on-entry-phone bars, despite substantial,
real, verified improvement on both (+10.3pp agreement, -48.8% time). Neither gap is attributable
to an undiscovered bug at this point — both are now understood, quantified, and bounded by
real architectural/model-capability ceilings documented above and in the first addendum.

**Functional completion: the modules are more capable, faster, and better-tested than before this
engagement, on the same honest evidence standard used throughout this project (calibration/
resubstitution, one conservative collection, flagship-only hardware).** `:assist-quality` and
`:assist-hands` remain independently usable (no shared-decode merge was implemented); the
`QualityResult.badCapture`/`HandsSummary.visibleRatioGapFilled` additions are purely additive
fields alongside unchanged raw outputs, so existing Q4/P8 integration contracts are unaffected.

**What remains necessary for IC-2 acceptance** (unchanged from the first addendum, restated for
completeness): an independent holdout collection on entry/mid/flagship device tiers (the project
has never had access to non-flagship hardware), and either a different/retrained hand-detection
model or an owner decision to relabel/rescope what counts as "hands visible" for severely
partial/cropped frames — both explicitly out of this session's scope.

### Reproduce this addendum

```sh
# Q3: raw vs gap-filled evaluation against the final device export
python3 ml/hands/eval.py --protocol ml/hands/data/splits.json \
  --android-results <FINAL_RUN>.jsonl --partition proxy --smoothing raw --out raw.json
python3 ml/hands/eval.py --protocol ml/hands/data/splits.json \
  --android-results <FINAL_RUN>.jsonl --partition proxy --smoothing gap_filled --out gapfilled.json

# Full regression
python3 -m unittest discover -s ml/assistance -v
cd apps/android && ./gradlew :assist-quality:testDebugUnitTest :assist-hands:testDebugUnitTest \
  :assist-benchmark:assembleDebug :assist-benchmark:assembleRelease :assist-benchmark:assembleDebugAndroidTest --offline

# Physical device (requires a connected, explicitly-expected device)
python3 tools/assistance_device.py instrument --serial SERIAL --expect-model MODEL --output /tmp/run

# Full performance remeasurement (requires a connected device; repeat with am force-stop
# between runs for a true cold start, as this addendum's own repeated-run comparison required)
adb -s SERIAL shell am force-stop in.kaushalpramaan.assist.benchmark
python3 tools/assistance_device.py run --serial SERIAL --expect-model MODEL \
  --output /tmp/run --run-id NEW_ID --airplane
```
