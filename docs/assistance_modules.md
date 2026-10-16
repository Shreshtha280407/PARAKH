# Offline technical-quality and hand-presence assistance

The libraries use real Kotlin metrics and a bundled CPU Hand Landmarker. Production
`:app` now consumes both libraries through a durable background coordinator. Current
versioned assets and decoder optimisations are preserved; this integration changes no
thresholds, model, sample rate or resolution. The latest inherited proxy figures are Q2
precision/recall 92.5%/92.5%, Q3 gap-filled agreement 75.8% and combined runtime
21.6 s/video-minute on the OnePlus 13R. These are calibration measurements, not new
independent field acceptance. See the recovery addenda below and
[the integration report](evidence/IC2_Q4_P8_integration.md).

## Owner-approved scope revision (2026-10-14)

The [master-plan amendment](Q2_Q3_master_plan_amendment.md) also approves functional
proxy evaluation using only the supplied collection and connected OnePlus. No independent
holdout, additional collection or field-generalisation proof is claimed. Original entry/mid
and IC-2 performance guarantees are unverified, outside this amended functional delivery.

Q2 covers technical exposure, blur and temporal camera motion. Automatic semantic
task-target framing is unsupported and outside the revised Q2 gate. This is an explicit
change from the original master plan. Original Out_of_frame labels and samples remain;
their exposure/blur/motion are assessed normally. Missing an intended target alone does
not make a clear, stable, well-exposed capture technically bad.

Q4/P8 integrates these modules, capture guidance and human review. No automatic
semantic-framing solution is promised. Any future method needs a separate target/context
design and validation. Hands do not establish interaction, competence, safety or identity.

## Module contracts

`:assist-quality` contains pure Kotlin luma/Laplacian/motion calculations, a bounded
read-only Android decoder and coroutine photo/video APIs. `:assist-hands` reuses that
decoder/sampler and runs the bundled pre-trained Hand Landmarker on CPU. Both are
production `:app` dependencies. `EvidenceRepository` schedules after capture promotion;
`EvidenceAssistanceCoordinator` persists identities/states in Room v6 and schedules unique
WorkManager jobs. `AssistanceRunner` permits one native analysis at a time, rejects stale
generations/revisions/hashes and stores compact typed results. Worker evidence/final previews
show advisory states and safe retry/cancel controls. P5 freezes a signed snapshot of the
exact final bytes without waiting for inference; P6 verifies/uploads it; the existing
assessor gallery shows flags and seekable timelines. Scoring/report rules are unchanged.
`:assist-benchmark` remains a separate package with no network or public-storage
permission, database, account or Keystore integration.
MediaPipe's transitive AAR declares network permissions; the harness explicitly removes
them in its own manifest. The library does not remove legitimate network permissions
from a consuming app: production retains the P6 network-security boundary. Model assets
are bundled once through the library and stored uncompressed (`.task`) in debug/release;
there is no runtime model download or public-storage import.
The production manifest removes the transitive DataTransport/CCT telemetry discovery and
upload components; merged debug/release checks and physical package inspection enforce
their absence. This preserves P6 networking without enabling the library statistics uploader.

All public timestamps are requested source-relative integer milliseconds. The default
sequential decoder selects the first frame at/after the request, or an EOS candidate no
more than 100ms before it. It applies container rotation exactly once. The optional
platform comparison path returns a nearby frame with rotation already baked. Do not
rotate module output again. Photo EXIF
orientations 1–8 are baked before aspect-preserving downscale. No evidence is rewritten.
Image decoding first reads bounds, uses power-of-two subsampling and then bilinear resize;
quality uses <=320px longest edge, hands <=640px. Tiny/corrupt/unsupported inputs fail
explicitly. Video is capped at 20 minutes, <=4096 per dimension and <=9MP; source codec
buffers are native allocations beyond the small returned bitmap and must be measured.

Quality luma is `(77R+150G+29B+128)>>8`, on gamma-encoded RGB. Clipping fractions count
Y<=16 and Y>=235. Blur is the population variance of a four-neighbour Laplacian on the
interior (one-pixel border omitted). Small frames without an interior return unavailable
blur. Low texture, underexposure, haze and compression affect this sharpness heuristic;
it is not a diagnosis of optical defocus. The versioned asset is the threshold source. Low-texture clear images can be falsely
flagged blurry; broad white content can trigger the saturation guard. Real positive
overexposure cases were not present: that guard has synthetic verification only.
Video on API26+ defaults to bounded sequential MediaCodec/YUV420 decoding, materializing
only selected small RGB frames with explicit SDR colour conversion, rotation and nearest-
neighbour sampling. HDR/unsupported pixel formats fail explicitly. The API27+ platform
retriever remains a comparison path, not the calibrated default. Physical tests compare
rotated pixels on both paths; forcing code paths on newer hardware does not establish
legacy-phone performance.
`review` severity is an assistance hint; observed metrics/thresholds are not probabilities.

Quality video sampling uses 1s anchors plus partners 125ms later. On 4x4 box-reduced luma,
nine textured tiles search translations +/-4px with brightness-centred absolute error.
Tile luma variance must be>=25. At least five textured tiles and 2/3 agreement within a +/-1px neighbourhood of
motion vectors, with bounded residual, are required. The cluster median estimates
translation; this tolerates integer matching variation without letting a moving minority
override a stable background. This distinguishes some local object motion from coherent image
motion. Rotation, large displacement, low texture, rolling shutter and occlusion can be
unavailable. It cannot reliably distinguish an intentional pan from unintended movement
or infer every shake event. Raw differences are reported separately and never called
camera shake. Motion coverage is explicit; unreliable pairs make the result partial.

Hands samples at 1fps, with up to two hands. The original confidence parameters were
0.5; the current detection floor is 0.1 with presence/tracking 0.5, as documented in the
pre-existing recovery addendum below. CPU is the baseline; native thread defaults are used, not a claimed fixed
thread count. Gloved-hand coverage is not established. A fresh VIDEO engine per clip guarantees ordered timestamps starting at 0;
photo inference uses a separate IMAGE engine. Returned hand counts support presence,
visible ratio and sampled absence intervals; landmarks/identity data are not retained.
Partial/occluded hands can be missed. The initial complete proxy comparison yielded
65.5% agreement (214 TP/164 FN/97 TN/0 FP on475 judgeable timestamps). Model-detected
absence is not verified physical absence; false negatives are substantial in this collection.
No >=90% agreement or field-generalisation guarantee is claimed. Decode/inference failures and structurally tiny
images are explicit states, excluded from ratio rather than counted absent. Severe
dark/blur ambiguity in *evaluation truth* is independently marked unjudgeable; successful
inference does not establish human judgeability.

Intervals represent left-anchored sample cells `[t,min(t+step,duration))`, not continuously
observed exact entry/exit times. Failed/unjudgeable samples break runs. Coverage counts
and represented duration must accompany flags. Both analyzers release bitmaps/readers
and the native engine in `finally`. Coroutine cancellation propagates as
`CancellationException`; native synchronous decode/inference can only be interrupted at
the next bounded sample boundary. Optional sample callbacks run on the analysis thread.

## Model provenance

Bundled [official version 1 model](https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task):
7,819,105 bytes, SHA-256
`fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`.
The [official model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20%28Lite_Full%29%20with%20Fairness%20Oct%202021.pdf)
states Apache License 2.0 (PDF p. 2); its SHA-256 and the full upstream licence are recorded
with `hands/model.json`. No runtime model download or server inference exists. Dependency:
`com.google.mediapipe:tasks-vision:0.10.35`, verified present in official Google Maven
metadata. Configuration bytes and model bytes receive separate hashes in reports.

## Local execution and production integration

See `ml/assistance/README.md` for private dataset intake/review. Library benchmarks remain
in the isolated harness. Production integration instrumentation uses isolated encrypted
databases, unique synthetic assessments and scoped cleanup. Build the libraries with:

```sh
cd apps/android
./gradlew :assist-quality:testDebugUnitTest :assist-hands:testDebugUnitTest \
  :assist-benchmark:assembleDebug :assist-benchmark:assembleRelease \
  :assist-benchmark:assembleDebugAndroidTest
```

After an explicitly selected physical device is connected, install only the two harness
APKs with `adb -s SERIAL install -r`; do not uninstall or clear either production or
harness data. `tools/assistance_device.py --help` provides stage/run/collect/instrument
commands, requiring serial and expected model. Stage streams originals into app-private
test storage and verifies hashes. Run waits for the completion artifact, not `am start`.
Existing run IDs are refused. Source/version stamps must match the staged plan.
Private raw gray exports stay outside Git; only redacted scalar evidence is durable.
Peak process PSS/native allocation is sampled approximately every 100ms, an observed
peak rather than a kernel lifetime maximum. Initialization, first inference, subsequent
warm inference, decoding/preprocessing, module wall time including reader/model close,
and combined wall time including result writes are reported separately. Historical
pre-close timing limitations are identified in the benchmark reports. Flagship measurements cannot satisfy entry/mid-range gates.

The coordinator uses the existing coroutine APIs,
for example `QualityAnalyzer.bundled(applicationContext).photo(file)` or `.video(file)`,
and `HandsAnalyzer(applicationContext).photo(file)` / `.video(file)`. WorkManager owns
production analysis across Activity recreation; leaving a screen does not cancel it.
Explicit cancellation invalidates the generation before cancelling work. Preserve
`CancellationException` in independently consumed library calls.
Treat SUCCESS, PARTIAL, FAILED and UNAVAILABLE distinctly: PARTIAL observations retain
usable metrics/flags alongside incomplete motion/sample coverage; missing profiles/models
must not become a successful analysis. A result with no detected hands is a model output,
not a finding that the worker failed to work. Represent semantic framing as unsupported,
never infer it from hands or technical flags.

Production stores errors, coverage and provenance alongside intervals, without landmarks
or verbose frame diagnostics. Changed optimisation/trim bytes receive fresh analysis;
SHA-256-equivalent bytes with equal duration can reuse results. Pending or unavailable
analysis does not block sealing. Sealed and inherited snapshots are immutable, including
historical revisions. See the [signed contract](evidence_quality_result.md),
[Q4 device protocol](gates/Q4_device_protocol.md) and [P8 gate](gates/P8.md).
Implemented integration does not establish original IC-2 or P8 field acceptance.

## 2026-10-15 recovery iteration addendum

`:assist-quality` now also exposes `QualityResult.badCapture: Boolean?` — a combined
clip-level review hint computed by the new `QualityVerdict` object from the same disclosed
per-sample flags/intervals (null when unavailable). It is still exactly a `review` hint: not a
probability, not competence, and it still never blocks evidence submission. Its policy (a
per-condition minimum consecutive-anchor run before a flag counts, and CAMERA_MOTION excluded
from gating the verdict while still computed/exposed) was fit on the same calibration data as
every other threshold here and is documented with full evidence in
[the recovery-iteration report](gates/Q2_Q3_recovery_iteration.md), which also records the
improved Q2 video precision (94.4% vs. the original 60.7%) this change produced — now confirmed
by actual Android/reference parity execution on a connected device, not only Python calibration.

`:assist-hands`'s `HandSample` now also carries `handConfidences: List<Double>` — the
handedness-classification score MediaPipe returns per already-detected hand. This is diagnostic
only: it does **not** let a lower detection floor be simulated after the fact, because
MediaPipe's Tasks API never returns a hand that failed the floor configured at inference time.

**2026-10-15, device-verified update**: `min_detection_confidence` is no longer an untuned
library default. A real on-device sweep (0.5/0.3/0.1/0.05, and jointly with presence/tracking)
found the lowest practical value, 0.1, recovers the most true positives with **zero measured
false-positive cost** (specificity stayed exactly 100% at every candidate tested) and that the
gain plateaus there — lower values or also lowering presence/tracking add at most 3 more true
positives out of 139 remaining misses. Shipped: `min_detection_confidence: 0.1`
(presence/tracking left at their original 0.5). Hands agreement improved **65.5% → 70.7%**
(sensitivity 56.6%→63.2%, specificity unchanged at 100%) but does not reach the original ≥90%
bar; the plateau itself is evidence that most remaining misses are a model-capability limit
(partially-visible/cropped hands the detector never proposes a candidate region for at any
confidence), not a threshold-selection problem. `HandsAnalyzer`'s delegate (CPU/GPU) is now
configurable from `model.json` instead of hardcoded; GPU delegate was measured (~2x faster
inference, no meaningful accuracy difference) but is **not shipped as the default**, since this
project has never had access to non-flagship hardware to verify GPU driver behaviour there. Full
sweep table, exact confusion matrices and the GPU comparison are in
[the recovery-iteration addendum](gates/Q2_Q3_recovery_iteration.md#addendum-device-verified-2026-10-15).

**2026-10-15, decoder bug-fix update (same day, continued)**: two genuine root-cause bugs were
found and fixed in `SequentialVideoDecoder`, not configuration tuning — it was speculatively
running the full YUV→RGB conversion on up to 4 frames per sample instead of 1 (fixed: defer
conversion until the matching frame is confirmed), and it read pixel buffers one bounds-checked
element at a time instead of bulk-copying each plane once per frame (fixed). Both proven
bit-exact (Q2/Q3 Android/reference parity and all 7 physical tests unchanged before/after).
Result: combined video-minute time dropped **42.22s → 21.60s (48.8% reduction)**, reproduced
across 3 cold-start runs. `:assist-hands` also gained `HandSample`-level gap-fill temporal
smoothing (`HandsSummary.visibleRatioGapFilled`/`handsNotVisibleIntervalsGapFilled`, additive —
raw fields unchanged): an isolated single-sample miss bracketed by detections on both sides is
reinterpreted as present, structurally incapable of bridging a real ≥2-sample absence. Hands
agreement improved **70.7% → 75.8%** (specificity unchanged at 100%, no false positives
introduced). Full root-cause detail, per-run performance table, and updated gate statuses are
in [addendum 2](gates/Q2_Q3_recovery_iteration.md#addendum-2-decoder-root-cause-fixes-and-q3-temporal-smoothing--2026-10-15-continued).
Neither the original ≥90% Q3 bar nor the ≤5s/video-minute bar is met; both gaps are now
architectural/model-capability, not further bugs.

Historical pre-recovery [Q2 report](../ml/quality/reports/quality-proxy-v2-final.json),
[Q3 report](../ml/hands/reports/hands-proxy-final.json),
[device benchmark](evidence/Q2_Q3/oneplus13r-benchmark-final.json) and
[acceptance matrix](gates/Q2_Q3_acceptance.md) retain the original measurements.
Their Q2 precision84.6%/recall92.5%, video precision60.7% and 11/22 good-video false
warnings predate the recovery above. Do not present them as the current v3 result or
reinterpret their scalar exports with newer profiles. All hints remain nonbinding.

## 2026-10-16 production validation

The separate opt-in QA UID uses actual CameraX, normal encrypted Room and OS WorkManager.
The OnePlus run now covers worker navigation, retake/delete, killed-process recovery,
offline sealing, interrupted upload, targeted reassessment and persisted dashboard seeking.
[Evidence and source/APK identities](evidence/IC2_Q4_P8_20261016.md) include the native R8
fixes: SQLCipher JNI entry points, MediaPipe callbacks and protobuf-reflected fields must
survive shrinking. No analyzer/model/threshold/sample-policy changes were made.
Only QA debug includes the read-only observer; normal debug/release exclude it.
P8 C/D/E pass for executed scenarios; independent A/B and entry/mid/three-phone checks
remain NOT VERIFIED. Original IC-2 remains FAIL because Q3 agreement is 75.8%.
