# Q2/Q3 functional acceptance — owner-amended scope

Status: **PASS — owner-amended functional scope implemented and verified locally.** No original-plan
field-generalisation, independent holdout, entry/mid or IC-2 acceptance is claimed.
The governing [master-plan amendment](../Q2_Q3_master_plan_amendment.md) replaces the
previous additional-data/independent-holdout prerequisites with functional offline
assistance on the original proxy collection and available OnePlus. It is a completed
scope decision, not deferred collection. No model training/fine-tuning was performed.

## Source and data identity

- Branch `feature/q2-q3-quality-hands`; base/main `36e0178405b5ad84f410de51d664bac9cab6c1b0`
  contains merged P7 PR #8/head `496c6166a7a8fc6c2636627c73f3a207be6d2bd5`.
- Final assistance tree SHA-256: `66b49e8e4837eaff27c2d94032aca6699a4cef6f0429fb1ca88edc6dcf250d98`.
  APK embeds base + this source identifier; whitelisted uncommitted source/APK snapshots
  are preserved locally outside Git. Generated metadata/reports have separate hashes.
- Original ZIP SHA-256 `737226d9b97bddb32270dd98359d3accfc38109ef6191c2d638855196a2b15b0`;
  supplied PDF SHA-256 `9741597fab636e101b304ad53f0ff390bb8a6bbb858ff2d1d88ec2f273c59737`.
  Both originals remain unchanged. Root `.env` remains1247 bytes with its original timestamp;
  its contents were not used in this task.
- 190 raw files, all fully decodable:149 actual photos/41 actual videos. Two byte-duplicate
  pairs leave **148 photos/40 clips**. One misplaced/duplicated video is corrected in metadata,
  with original paths/bytes preserved. Byte uniqueness is not scene/session independence.
- Unique original categories, good/dark/blurry/motion/out_of_frame: photos30/29/29/30/30;
  clips8/9/8/7/8. Original hand folders21 visible/19 not-visible; direct review corrected15
  not-visible clips containing hands. All original annotations are retained separately.
- Quality truth:107 bad/80 good/1 ambiguous capture, all188 retained and analysed. Photos:
 90 bad/58 good. Clips:17 bad/22 good/1 ambiguous. Labels are independent direct visual
  review, not algorithm output. Camera motion is unjudgeable where moving foreground or
  severe darkness/haze prevents attribution; still motion blur is not camera-shake truth.
- Hand truth:40 unique clips,497 reviewed timestamps:378 present/97 absent/22 unjudgeable.
  Actual Android asks498 timestamps because duration rounding differs; one sample at11000ms
  in `m-9588ef917fe7` lies beyond the10994ms ffprobe reference (Android11042ms). It is
  explicitly unlabelled, not invented absent. Judgeable truth:475/497 reviewed (95.573%),
 475/498 Android requested (95.382%).
- Frozen `drive-proxy-functional-v1`, SHA-256
  `d32721b038cd42de22db3aceff40094bd971fb70e75a77581b4eb0ee33b05331`:
  one conservative group, all188 calibration, **zero validation/holdout**. Exact/near
  duplicates and repeated scenes remain together. Three source phones are not established.

## Requirement matrix

PASS means the stated functional scope has actual evidence. Original performance claims
excluded by the owner amendment are listed separately, without being converted into passes.

| Requirement | Implementation | Verification/evidence | Result |
|---|---|---|---|
| Protect project/phone data; P7 prerequisite; separate branch | Separate libraries/harness; production app has no dependency | Git ancestry/status, `.env` stat, unchanged ZIP hash; only harness/test `install -r` | PASS |
| Safe, complete and reproducible intake | `ml/assistance/intake.py`, manifest/audit/hash groups |190/190 full decode; traversal/symlink/type/overwrite tests; portable root argument | PASS |
| Honest labels, ambiguity and conservative grouping | Review JSON, exporters, CSVs and shared frozen protocol | Direct images/frames +125ms follow-ups; no predictions used for truth | PASS |
| Kotlin-only technical quality | `:assist-quality`, bounded adapters/pure metrics | Unit/golden/real-device rotation, tiny/corrupt/cancellation checks | PASS |
| Real versioned thresholds | `quality-proxy-v2`: dark60, photo blur400/video100, motion2; saturation245/.95 | Immutable calibration code/input/profile/protocol hashes; photo/video boundary test | PASS — actual final runtime/asset parity verified |
| Q2 actual Android/reference parity and proxy report | Gray exports, `check_android_exports.py`, `quality/eval.py` | [Final Q2 report](../../ml/quality/reports/quality-proxy-v2-final.json), scalar Android outputs and parity checks | PASS —148 photo metric exports/188 calibrated records |
| Offline pre-trained hand engine | `:assist-hands`; Tasks Vision0.10.35 CPU, max2, confidence.5,1fps | Official model/licence/SHA checks; asset in debug/release; real native tests | PASS |
| Hand ratios/intervals, failures and cancellation | Typed API; failures excluded, left-anchored cells, ordered source times | Unit tests + physical cancellation/repeat/corrupt; actual aggregation parity | PASS |
| Honest hand proxy evaluation/coverage | Independent497-sample review vs actual498 requests | Confusion, clip means, ratio error, absence IoU, transition tolerance and extra-sample audit | PASS — final498-request coverage/aggregation report |
| Actual USB offline execution on available flagship | Separate private Assistance Lab; no INTERNET/gallery permissions | All188 staged/hash checked; prior full runs complete; final physical7 tests pass | PASS — final188/188 capture run completed offline |
| Timings/memory/size measured without hardware substitution | Completed-run collector and scalar report tool | Actual init/first/warm/decode/preprocess/wall, sampled PSS/native, APK/AAR/model bytes | PASS — final benchmark/model/APK/AAR report |
| Regression/CI-safe checks |15 Python tests;17 module unit tests; synthetic fixtures; CI additions | Debug/release/AAR/test builds, lint;133 existing unit regressions; production security and418-string parity | PASS local; hosted CI not run |
| Technical cards and Q4/P8 contract | `docs/assistance_modules.md`, Q2/Q3 gates and workflow README | Errors/coverage/versions/timestamps, no automatic rejection/competence/framing promises | PASS — final self-audit and evidence reconciled |
| Reconcile P7 wording with merge/historical evidence | `docs/gates/P7.md` | PR#8 ancestry,114-file final diff,11 physical tests, historical225 preserved; four regression fixes described | PASS; fresh hosted CI unavailable and not invented |

## Explicit limits of the accepted functional scope

No independent holdout exists. Proxy calibration/resubstitution figures are descriptive,
optimistic for generalisation, and have correlated observations. One collection cannot
support an independent field confidence interval. Semantic target framing is unsupported;
Out_of_frame labels remain and missing a target alone is not technically bad.

The v1 audit found excessive video false positives from a shared photo/video blur cutoff.
V2 fits blur separately by modality; v1 code, thresholds and reports remain preserved.
Final source-matched Kotlin execution confirms Q2 precision84.615%/recall92.523% (TP99/FP18/FN8/TN62). Hand inference/configuration is unchanged:
final agreement65.474% (TP214/FN164/TN97/FP0), sensitivity56.614%, specificity100%.
Substantial missed hands and false quality warnings remain disclosed limits. Neither
library may reject evidence, force a retake or award competence from these outputs.

Original Q2 held-out precision>=85%/recall>=80%, Q3 independent agreement>=90%, three-phone
collection diversity, <=60ms/frame on representative mid-range hardware and <=5s/video
minute on entry hardware are **not accepted**. Proxy results do not meet/prove those
requirements. They are outside this owner-amended functional completion, not hidden passes
or deferred tasks required to finish it. OnePlus13R is flagship hardware; debug-device
measurements do not establish release/mid/entry performance. Hosted CI is unrun because
nothing is committed/pushed; local verification is recorded separately.

Q4/P8 will integrate typed advisory results, capture guidance and human review with later
manifest/storage/timeline work. It does not promise automatic semantic framing. Any future
automatic task-target method requires a separate defined design and validation.

## Final executed evidence

- [Q2 proxy report](../../ml/quality/reports/quality-proxy-v2-final.json):187 judgeable captures;
  one ambiguous clip retained/analysed. Photos P92.135%/R91.111%; videos P60.714%/R100%.
  Video good-capture false warnings11/22 remain a material limit; no original accuracy pass.
- [Q3 proxy report](../../ml/hands/reports/hands-proxy-final.json):40 clips,475 judgeable
  timestamps; TP214/FN164/TN97/FP0. All40 actual ratio/absence aggregations match reference.
  Extra/out-of-grid and unjudgeable points are separately counted. No >=90% claim.
- [Final benchmark](../evidence/Q2_Q3/oneplus13r-benchmark-final.json):OnePlus13R CPH2691,
  API36, arm64-v8a, Android totalMem11,758,895,104 bytes. CPU/default threads; hand input
  longest640px,1fps. Initialization mean79.234ms; warm inference458 samples mean99.731,
  p5091.439, p95198.441ms. Decode+preprocess+inference mean459.792ms/sample.
- Completed full run `final_full_v3`:383313.092ms. Quality12.723s/video-minute, hands29.466,
  combined42.218 including result writes. Android duration denominator480465ms; ffprobe
  unique total479155ms. Observed PSS peak199288KiB (~194.6MiB), native111547568 bytes.
  Memory has a100ms delay plus measurement overhead; no kernel maximum or thermal control claim.
- Quality149 SUCCESS/39 PARTIAL due explicit motion coverage (309/496 reliable pairs);
  hands188 SUCCESS. No decode/inference sample failures. An inference SUCCESS is not proof
  of correct presence classification or human judgeability.
- [Final physical transcript](../evidence/Q2_Q3/oneplus13r-instrumentation-final.txt):7/7
  tests passed in4.924s, including tiny PARTIAL, calibrated dark/saturation, EXIF/video
  geometry, native repeat/cancellation and corrupt inputs.17 module unit tests and15 Python
  workflow tests pass;16 golden vectors and133 unchanged-production unit regressions recorded.
- [Local verification](../evidence/Q2_Q3/local-checks-final.json);
  [durable scalar Android output](../../ml/assistance/reports/oneplus13r-functional-final-results.jsonl).
  No private images/videos/frames/gray pixels/landmarks were copied into Git. The two tiny
  committed-candidate test videos are generated synthetic fixtures.
- Debug APK57,425,685 bytes; unsigned release56,503,875; quality release AAR76,038; hands
  release AAR5,886,975. Bundled model7,819,105 bytes; detailed native/model contributions
  and artifact SHA-256 values are in the benchmark. Release is built/packaged, not physically
  run; device measurements use the isolated debug harness.
- Airplane mode was restored to0 after completion. Existing PARAKH app/data/assessments,
  root `.env`, ZIP/original media and signing/account/database state remain preserved.
- No commit, push or PR. Hosted CI is unrun; the owner will manually publish after review.
