# Reproducible local assistance evaluation

The [owner-approved master-plan amendment](../../docs/Q2_Q3_master_plan_amendment.md)
uses only the original proxy collection. It is one conservative calibration group, with
no independent validation/holdout or field-generalisation claim. Dataset/review/protocol
metadata stays in Git; originals, extracted frames, private gray exports and raw USB logs
stay outside Git. Intake/review uses no model. Q3 ground truth is direct visual review,
never MediaPipe predictions. No training/fine-tuning pipeline exists.

Local prerequisites: Python 3.10+, Pillow, ffmpeg/ffprobe; Android SDK/ADB and the project’s
pinned Gradle/JDK toolchain for actual Kotlin/device execution. CI uses synthetic pixels,
two tiny generated videos and the public bundled model; no Downloads/private-media path.

## Intake and reviewed truth

```sh
python3 ml/assistance/intake.py --zip /path/to/original.zip --dataset-root /tmp/parakh-q2-q3-20261014
python3 ml/assistance/review.py --dataset-root /tmp/parakh-q2-q3-20261014
python3 ml/assistance/export_quality_labels.py
python3 ml/assistance/export_hand_labels.py
```

Intake validates every archive entry before extraction (absolute/traversal/Windows paths,
symlinks/special files, encryption, duplicate entry names and size limits), refuses changed
originals, verifies hashes and fully decodes every file. It records actual media type,
dimensions/orientation, codec/fps/duration, safe source metadata, exact duplicates and
rotation-aware dHash candidates. The misplaced video is corrected in metadata, never moved.
Paths are relative to `--dataset-root/originals`. Full video decode streams to a null sink;
review keeps bounded small images outside Git.

`initial_labels.csv` contains unverified owner folder annotations. The versioned visual
review JSON files are manually curated observations; exporters validate identity/hash,
retain original annotations and explicitly preserve unjudgeable conditions/captures.
Hand labels cover requested 1s timestamps, with sampled transition brackets and absence
cells. Photos/video stills are not independent derivative samples. Messaging-style names,
missing metadata and a device model name do not establish recording-session/device count.

The frozen `quality/data/splits.json` (identical `hands/data/splits.json`) assigns all 188
byte-unique captures to the same conservative collection group. No media was dropped to
create artificial independence. The one ambiguous quality clip is still analysed and its
exclusion from quality accuracy is reported. Reviewed hand ambiguity is excluded only
from judgeable-truth comparisons, never relabelled absent. Existing frozen versions cannot
be overwritten. To reproduce the original freeze in a new checkout without that output:

```sh
python3 ml/assistance/freeze.py --manifest ml/quality/data/manifest.jsonl \
  --quality-labels ml/quality/data/labels.csv --hand-sample-labels ml/hands/data/sample_labels.csv \
  --assignments ml/quality/data/assignments.csv --near-duplicates ml/quality/data/near_duplicate_candidates.json \
  --out ml/quality/data/splits.json --version drive-proxy-functional-v1 \
  --design owner_approved_proxy_resubstitution --owner-scope-amendment docs/Q2_Q3_master_plan_amendment.md
```

A newly generated freeze has a new UTC timestamp/hash and requires a newly versioned
calibration. The checked-in frozen metadata is the exact release provenance; do not
regenerate it in place. Independent-design guards remain available, but refuse missing
independent partitions. Proxy evaluation cannot be called held-out evaluation.

## Actual Android metrics, deterministic calibration and evaluation

Build/install only the separate `:assist-benchmark` app/test packages. Use `adb -s SERIAL
install -r` for these packages; never uninstall, clear data or run production connected-test
installation. Serial and expected model are mandatory in the USB runner. For example:

```sh
python3 tools/assistance_device.py stage --serial SERIAL --expect-model MODEL \
  --dataset-root /tmp/parakh-q2-q3-20261014 --output /tmp/assistance-run --repeats 1
python3 tools/assistance_device.py run --serial SERIAL --expect-model MODEL \
  --output /tmp/assistance-run --run-id NEW_UNIQUE_RUN_ID --airplane
python3 tools/assistance_device.py collect --serial SERIAL --expect-model MODEL \
  --output /tmp/assistance-run --run-id NEW_UNIQUE_RUN_ID --gray
```

Binary-safe shell-v2 transfers are checksummed on both sides. Existing run IDs are refused;
completion comes from the harness’s done file, not activity scheduling. Airplane mode is
restored to its prior state. No network/public-storage permission is present. Stage before
running; build/source-stamp mismatches fail explicitly. Model and native codec resources
are released between analyses; failure is not an absent hand or accepted quality result.

The first full metrics run uses the uncalibrated profile, returning observed metrics and
PARTIAL/no advice. Fit deterministic thresholds only after truth/protocol freeze:

```sh
python3 ml/quality/tune.py --protocol ml/quality/data/splits.json \
  --android-results /tmp/assistance-run/METRICS_RUN.jsonl \
  --metrics-profile /tmp/metrics-apk/thresholds.json \
  --version NEW_QUALITY_VERSION --out apps/android/assist-quality/src/main/assets/quality/thresholds.json
```

This is finite-grid deterministic threshold calibration, not model training. Condition-wise F1, precision/recall and conservative ties select dark first, separate
photo/video blur thresholds, then camera motion. This avoids imposing photo sharpness
distributions on compressed video. The earlier shared-blur v1 report/code is preserved;
v2 corrects its excessive false-positive rate without changing reviewed truth. Grid: dark mean20..110 step5, Laplacian
variance5/10/20/30/40/60/80/100/150/250/400/700 for each modality, motion1..5 reduced-image pixels. Underexposure
suppresses an unsupported defocus claim. Highlight mean>245 plus clipping>0.95 is a fixed
conservative saturation guard, tested synthetically; no real positive highlight validation
is claimed. Each calibration version is archived immutably, with input/protocol/code hashes.

Rebuild/reinstall/restage the calibrated asset, then rerun the full collection on Android.
Run these one-command checks against those *new completed* exports:

```sh
python3 ml/quality/check_android_exports.py --results /tmp/assistance-run/CALIBRATED_RUN.jsonl --gray-dir /tmp/assistance-run
python3 ml/quality/eval.py --protocol ml/quality/data/splits.json --partition proxy \
  --android-results /tmp/assistance-run/CALIBRATED_RUN.jsonl --out ml/quality/reports/NEW_VERSION.json
python3 ml/hands/eval.py --protocol ml/hands/data/splits.json --partition proxy \
  --android-results /tmp/assistance-run/CALIBRATED_RUN.jsonl --out ml/hands/reports/NEW_VERSION.json
```

These are calibration/resubstitution descriptions, not independent performance estimates.
One photo or unique clip has one capture weight; frame and clip results are separate.
Report per-condition/type/category confusion, unavailable observations, hand sensitivity/
specificity, ratio error, absence-cell IoU and transition tolerance. Samples within a clip
and the repeated collection are correlated; no independent field confidence interval is
justified. Re-running/reshuffling cannot manufacture untouched test data.

## CI-safe checks and physical evidence

```sh
python3 -m unittest discover -s ml/assistance -v
python3 ml/quality/generate_vectors.py --check
python3 tools/verify_assistance_assets.py --require-calibrated
```

See [module cards and integration contract](../../docs/assistance_modules.md) for Gradle
build/tests, and the Q2/Q3 gates for actual executed hardware evidence. Instrumentation
uses `tools/assistance_device.py instrument` and only the separate test package. The
source-stamp helper can preserve a whitelisted source archive outside Git with
`--snapshot-dir`; dataset/review/protocol/result hashes are recorded separately. Peak PSS
is sampled about every100ms, an observed peak rather than a kernel lifetime maximum.
OnePlus13R is flagship hardware. Original entry/mid and IC-2 claims remain unverified.

Historical v1 calibration scalar exports and the exact Android metrics profile are in
`ml/quality/calibration/`. v2 reuses those unchanged metric definitions/input hashes and
changes threshold calibration only. Never overwrite the immutable v1/v2 archive files.
The final full scalar run belongs in `ml/assistance/reports`; no pixels/landmarks are stored.
Android/ffprobe duration rounding differs: report every extra Android timestamp outside
the independent review grid as unlabelled, alongside reviewed-unjudgeable samples and
both coverage denominators. Do not count those as absent or silently drop them.

The CI replay step reads only the durable scalar final Android output and frozen metadata.
It checks threshold/ratio/interval arithmetic and provenance; it does not run inference or
claim new hardware/field evidence. Final acceptance is recorded in
[the combined matrix](../../docs/gates/Q2_Q3_acceptance.md).

## Quality-proxy-v3: clip-level aggregation recalibration (2026-10-15)

`tune.py` now also fits the clip-level verdict policy — `clip_bad_fraction`, a per-condition
minimum consecutive-anchor run length, and whether `CAMERA_MOTION` counts toward the combined
verdict at all — by finite grid search over the same frozen calibration partition, scored by
combined F1 subject to a hard recall>=0.80 floor (see `aggregation_fit` in the archived
profile). Per-frame DARK/BLURRY/CAMERA_MOTION thresholds are unchanged from v2. Reproduce:

```sh
python3 ml/quality/tune.py --protocol ml/quality/data/splits.json \
  --android-results ml/quality/calibration/quality-proxy-v2-android-metrics.jsonl \
  --metrics-profile ml/quality/calibration/quality-proxy-v2-metrics-profile.json \
  --out apps/android/assist-quality/src/main/assets/quality/thresholds.json --version quality-proxy-v3
python3 ml/quality/report_v3_calibration.py
```

`report_v3_calibration.py` is **not** an Android/reference parity report (`eval.py` correctly
refuses that claim: the exported Android metrics were captured under the v2 asset hash, and
v3's per-frame thresholds — the only thing that hash pins — are byte-identical to v2's
already-parity-verified values; only the aggregation *policy*, a pure post-processing step
over already-verified per-sample flags, changed). It is the same calibration/resubstitution
description v1/v2's headline numbers always were. A literal on-device run of the v3 asset,
re-verifying per-sample flag parity end to end, is a separate, currently NOT VERIFIED step —
see [the recovery-iteration report](../../docs/gates/Q2_Q3_recovery_iteration.md).

## Independent holdout collection checklist (not yet executed)

No independent validation/holdout partition exists; `evaluation_design` remains
`owner_approved_proxy_resubstitution` with one calibration group. To add one without leaking
into calibration:

1. Record new sessions on devices/lighting/backgrounds distinct from the original collection,
   explicitly noting device model, lighting condition and session id per file (the current
   collection cannot establish these, which is exactly what blocked grouping before).
2. Intake into a **separate** dataset root: `python3 ml/assistance/intake.py --zip NEW.zip
   --dataset-root /tmp/<new-root>`, then `review.py`/`export_*_labels.py` as above, producing
   independently reviewed truth with no reference to model predictions.
3. Freeze a **new** protocol version with `--design independent_grouped` (not
   `owner_approved_proxy_resubstitution`) and non-empty `validation`/`heldout` partitions,
   assigning every new session's group to exactly one partition — `freeze.py` already refuses
   split partitions for files `load_protocol` recognises as a shared group/`original_collection_ids`.
4. Evaluate with `--partition heldout` (never `proxy`) against the **already-frozen** v3
   thresholds — do not retune on heldout data; a failing heldout result must be recorded, not
   discarded or quietly re-fit.
5. Device-tier benchmarking (`tools/assistance_device.py`) must name the actual device tier
   (entry/mid) in its report; a flagship re-run can never stand in for that gate.
