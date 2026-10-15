# Q2/Q3 progress and acceptance record

Updated2026-10-14 (final audit18:25UTC): **owner-amended functional scope implemented and verified locally.**
Authoritative [acceptance matrix](Q2_Q3_acceptance.md), [master-plan amendment](../Q2_Q3_master_plan_amendment.md),
[Q2 gate](Q2.md), [Q3 gate](Q3.md). No commit/push/PR; owner will manually publish.
No outstanding task under the amended functional scope. Original field/entry/mid/IC-2
claims are unverified and excluded, never converted into passes or deferred data requests.

## Owner decisions and boundaries

Q2 is technical exposure, blur and temporal camera-motion assistance; semantic task-target
framing is unsupported. Original Out_of_frame annotations/media remain and are technically
evaluated. Hand presence does not establish framing, work, identity, competence or safety.
Proxy household/switch/MCB footage is not real-trade competence validation. Q4/P8 integrates
advisory results, capture guidance and human review; automatic framing needs separate
future design/validation and is not promised. Production capture/seal/sync/scoring untouched.

The owner initially agreed to two new capture sets, then explicitly cancelled collection
and approved functional verification using only the original proxy data and available
OnePlus. No model training/fine-tuning, new field data, independent holdout or entry/mid
performance acceptance is required for this amended delivery. Numeric proxy results and
known limits remain explicit. No further data/hardware question is pending.

## Fixed source/data identifiers

- Branch `feature/q2-q3-quality-hands`. Base/main36e0178405b5ad84f410de51d664bac9cab6c1b0
  is merged P7 PR#8; P7 head496c6166a7a8fc6c2636627c73f3a207be6d2bd5 is an ancestor.
  Starting tree was clean; no applicable AGENTS.md in repo/ancestors. Remote freshness/
  latest hosted P7 CI unavailable without HTTPS authentication; local main/cached origin
  agree. No invented hosted link/count.
- Final source: `36e0178405b5ad84f410de51d664bac9cab6c1b0+assistance-tree-sha256:66b49e8e4837eaff27c2d94032aca6699a4cef6f0429fb1ca88edc6dcf250d98`.
  Source/APK snapshots outside Git: `/tmp/parakh-q2-q3-device/oneplus-20261014/final-v3-source`
  and `final-v3-apk`. Source hashing excludes generated reports/data; their hashes are separate.
- Supplied PDF read (pp13/23/26: contracts, IC-2/P8, Q2/Q3/Q4); original SHA
  9741597fab636e101b304ad53f0ff390bb8a6bbb858ff2d1d88ec2f273c59737.
- Exact ZIP `/home/Shreshtha/Downloads/PARAKH_AI_Data-20261014T132710Z-1-001.zip`;
  SHA737226d9b97bddb32270dd98359d3accfc38109ef6191c2d638855196a2b15b0 rechecked unchanged.
  Extracted/review root `/tmp/parakh-q2-q3-20261014`; original files unchanged.
- Intake `proxy-intake-v2`:190 regular entries/998820428 uncompressed bytes, no unsafe paths/
  symlinks/encryption/duplicate entry names; **190/190 full decode**.149 actual photos/41 videos;
  two byte-duplicate pairs =>148 photos/40 clips. One video misplaced in photo folder is
  corrected in metadata, not moved. No private media/frames/gray files proposed for Git.
- Manifest SHA7ec33b6ad081b80d736243d489d19066657afce71ffbb1769ebf1b313ae2c60a.
  Unique original good/dark/blurry/motion/out_of_frame counts: photos30/29/29/30/30;
  videos8/9/8/7/8. H26423/HEVC17, rotations0/90. ffprobe unique duration479155ms;
  Android metadata480465ms, separately disclosed.35 photo EXIF OnePlus13R records,
 155 entries missing device info;137 messaging-style names. Three physical source phones
  cannot be established.95 rotation-aware dHash candidates conservatively grouped together.
- Quality independent direct review:107 bad/80 good/1 ambiguous; photos90/58, clips17/22/1.
  Review files/exported labels preserve original categories and per-condition uncertainty.
  Hands:40 unique clips/497 review timestamps,378 present/97 absent/22 unjudgeable;15 original
  not-visible clips corrected. No MediaPipe predictions used as truth.
- Frozen protocol `drive-proxy-functional-v1`, SHA
  d32721b038cd42de22db3aceff40094bd971fb70e75a77581b4eb0ee33b05331; all188 in one conservative
  calibration group, zero validation/heldout. Exact/near duplicates/scenes remain together.
- Quality `quality-proxy-v2`, asset SHA46fc919412acd9428e9966215825858ac1e7123ceffb2e181d31223830490127; dark60/photo blur400/video blur100/motion2,
  fixed saturation245/.95. Immutable calibration code/input/profile archives in `ml/quality/calibration`.
- Hand task official float16/v1,7819105 bytes/SHA
  fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1, Apache2 model-card evidence,
  Tasks Vision0.10.35, CPU/default threads/max2/confidences.5/1fps/longest640px. Config SHA
  49f57abe43c482e9647b2d4b515cdd32159e47689239916cd84c12a72f27f291.

## Final actual results

- `final_full_v3` COMPLETED all188 quality +188 hands analyses offline on OnePlus13R,
  CPH2691/API36/arm64-v8a/Android totalMem11758895104 bytes. Airplane1 during run,
  restored0 afterward. Only separate harness/test packages installed with-r; no production
  PARAKH reinstall/clear/uninstall, assessment/Keystore/account/database/signing-key changes.
- Q2 Android/reference PASS148 photo gray metrics and188 calibrated flag records. Quality
 149 SUCCESS/39 PARTIAL due motion coverage309/496 pairs; no decode/inference sample failures.
  Q2 proxy TP99 FP18 FN8 TN62, P84.615%/R92.523% on187 judgeable captures; ambiguous clip
  retained/analysed. Photos P92.135/R91.111; videos P60.714/R100, false warnings11/22 good clips.
- Q3 actual40-clip aggregation parity PASS.475 judgeable references: TP214 FN164 TN97 FP0,
  agreement65.474%, sensitivity56.614%, specificity100%. Substantial misses/false absence
  intervals remain; no >=90% performance claim. Android requests498, reference review497;
 22 reviewed-unjudgeable plus1 unlabelled beyond-grid point explicitly reported. Judgeable
  coverage475/497=95.573% reviewed or475/498=95.382% Android requested.
- Completed wall383313.092ms; quality12.723s/video-minute, hands29.466, combined42.218
  including writes. Warm hand458 samples mean99.731/p5091.439/p95198.441ms. Init mean79.234ms;
  first video inference mean60.990ms; decode+preprocess+inference mean459.792ms/sample.
  Observed PSS199288KiB (~194.6MiB), native111547568 bytes.100ms sampler delay plus overhead;
  debug harness/USB/consecutive runs, no thermal/cold-storage or kernel-maximum claim.
- Debug/release APK57425685/56503875 bytes; quality/hands release AAR76038/5886975 bytes;
  four-ABI standalone harness. Model/native entry contributions and artifact hashes in report.
  Release built/packaged, not physically run. No entry/mid/IC-2 substitution.
-17 module unit tests (quality14/hands3),15 Python workflow tests,16 independent synthetic
  vectors and7 physical tests PASS (final4.924s). Existing133 core/mapping/budget/media/seal/app
  unit regressions and relevant lint/build/security checks passed; production source unchanged.
  EN/HI418 values/3 files/26 cards parity PASS. CI additions use only synthetic fixtures,
  public model and metadata; hosted CI unrun because no authorised publication.
- P7 docs corrected merge/counts/Room/dashboard/11 physical tests/historical225 versus later
  regressions; majority-NOS, complete PDF hashes/wrapped text, transaction locking and repeat
  password checks documented. Historical revisions and .env incident preserved.

## Preserved development findings

Unsafe/truncated adb exec-in transfer was caught by SHA checks before analysis; corrected
to binary-safe shell-v2 with exit status. Transitive INTERNET permissions removed only from
harness. API27-only lint failure fixed with real API26+ sequential MediaCodec SDR/YUV decoding;
rotation checked by pixels on both decoder paths. V1 exact motion votes lacked coverage;
v2 neighbour-vector consensus added with local-motion/brightness/low-texture negatives.

Historical shared-blur quality-proxy-v1 had video20/22 false warnings; preserved source,
thresholds and reports led to separate photo/video calibration in v2 (now11/22). Frozen truth
unchanged. Extra native timestamp and tiny-image false SUCCESS were fixed explicitly.
Previous sourcef778... andcb73... reports remain historical, not attributed to final66b49... .

Authoritative durable outputs: `docs/evidence/Q2_Q3`, `ml/quality/reports/quality-proxy-v2-final.json`,
`ml/hands/reports/hands-proxy-final.json`, `ml/assistance/reports/oneplus13r-functional-final-results.jsonl`.
Raw media/gray exports and full logs remain outside Git; reproduce via `ml/assistance/README.md`.
Root.env still1247 bytes, original2026-10-14 16:35:04.164162983+0530 timestamp. No secrets printed.
