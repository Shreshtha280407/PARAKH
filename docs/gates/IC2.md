# IC-2 — production integration and original acceptance

Original acceptance: **FAIL / NOT ACCEPTED**. Functional implementation is separate from
accuracy, performance and field acceptance. The owner explicitly authorised this integration
before the remaining gates were met. The original PDF pages 23/26 and the owner-approved
[Q2/Q3 amendment](../Q2_Q3_master_plan_amendment.md) remain unchanged.

| Gate | Required | Evidence | Verdict |
|---|---|---|---|
| Q2 precision | ≥85% | 92.5% latest historical calibration/resubstitution report | PASS on proxy; independent acceptance NOT VERIFIED |
| Q2 recall | ≥80% | 92.5% same report | PASS on proxy; independent acceptance NOT VERIFIED |
| Q3 hands agreement | ≥90% | 75.8% latest historical CPU/gap-filled result | FAIL |
| Video analysis on entry phone | ≤5 s/video-minute | 21.6 s/video-minute on OnePlus 13R flagship; no entry device | NOT VERIFIED on required tier; observed flagship runtime exceeds target |
| Hands inference on mid phone | ≤60 ms/frame | No mid-range evaluation | NOT VERIFIED |
| Production Android integration | Functional capture → real inference → seal → sync | Actual OnePlus CameraX/worker navigation, OS analysis/upload process recovery, offline seal, sync and targeted recapture now verified | PASS on available device |
| Signed flag persistence | Signature + exact evidence/revision binding | Real Android Keystore signatures, HTTP/PostgreSQL uploads, exact stored-snapshot comparisons, resume/history/contract tests | PASS |
| Dashboard markers | Correct position and seeking | Persisted signed boundary fixtures plus actual CameraX recordings, protected player and historical/current labels | PASS for executed browser integration |
| P8 exit tests | Original bad/good capture + markers | New 10-bad/10-good production field run unavailable | NOT VERIFIED as a combined exit gate |
| Independent field validation | Separate representative evidence | No independent holdout or new three-phone field run | NOT VERIFIED |

The numeric proxy results above are inherited evidence, **not new measurements in this
integration session**. See the final addendum in
[Q2_Q3_recovery_iteration.md](Q2_Q3_recovery_iteration.md); historical source-matched
replays continue to use their original frozen profiles. No threshold, model, sample rate,
resolution, annotation or historical benchmark was changed to improve acceptance figures.

Current implementation, executed checks and explicit remaining work are recorded in
[the integration report](../evidence/IC2_Q4_P8_integration.md). Neither a successful build
nor the available OnePlus product-path run establishes independent field accuracy or required-tier performance. See the [October 16 continuation](../evidence/IC2_Q4_P8_20261016.md).
