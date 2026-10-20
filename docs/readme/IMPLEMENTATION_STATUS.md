# Implementation and evidence index

This is the technical companion to the product README. Gate documents record the scope and date of individual checks; their results are not cumulative test totals or current production guarantees.

| Milestone | Implemented scope | Evidence and boundaries |
|---|---|---|
| P1 | Source-pinned CON/Q0602 pack, five tasks, coverage and support rubrics | [Pack gate](../gates/P1.md), [completion report](../P1_TECHNICAL_COMPLETION_REPORT.md) |
| P2 / P2.1 / P2.2 | Backend, protected storage, lifecycle, scoring, report and token foundations | [P2.1](../gates/P2_1.md), [P2.2](../gates/P2_2.md) |
| Q1 / P3 | Deterministic single-QP matching; Kotlin/Python golden-vector parity; offline worker journey | [Q1](../gates/Q1.md), [P3](../gates/P3.md) |
| IC1A | Technical correctness and standards traceability | [Acceptance](../gates/IC1A.md); independent expert-agreement study was not performed |
| P4 | Real CameraX evidence, encrypted durable drafts, preview/retake/replace/delete | [Capture gate](../gates/P4.md); dated physical-device evidence |
| P5 | Automatic media optimization, deterministic budgeting, canonical signed manifest, encrypted vault and durable outbox | [Sealing gate](../gates/P5.md) |
| P6 | Resumable synchronization, server signature/hash checks, metadata jobs and protected assessor evidence | [Protocol](../gates/P6.md), [physical-device run](../gates/P6_physical_device_2026-10-14.md) |
| P7 | Computed profile, human override reasons, targeted revisions, sign-off and PDF integrity | [Gate](../gates/P7.md), [physical-device run](../gates/P7_physical_device_2026-10-14.md) |
| Q2 / Q3 | Offline technical-quality and hand-presence assistance | [Acceptance matrix](../gates/Q2_Q3_acceptance.md); calibration/proxy results, without independent holdout |
| IC2 / Q4 / P8 | Durable assistance integration, worker previews, signed flags and assessor timelines | [Integration report](../evidence/IC2_Q4_P8_integration.md); original independent-field exits remain incomplete |
| P10 | Assessor hardening, deployment tooling, regression and performance work | [P10 gate](../gates/P10.md), [measurements](../perf.md); retain the documented scope limits |
| Open access | Candidate PIN, consent-aware public summaries and coordinated release configuration | [Release notes](../deployment/OPEN_ACCESS_RELEASE.md); portions describe historical email-code review, superseded by password accounts |
| Assessor accounts / UX | Password-based assessor access, grouped scoring, navigation and sync UX | [Account and sync evidence](../evidence/ASSESSOR_PASSWORD_AND_SYNC_20261018.md), [review workspace](../evidence/DASHBOARD_REVIEW_UPDATE_20261018.md) |
| Universal signed reports | Positive and negative final decisions issue verifiable artifacts; publication consent stays separate | [Report regression](../evidence/UNIVERSAL_SIGNED_REPORTS_20261019.md) |

## Checks run for the README

On 20 October 2026, the following were run against the working checkout:

- Pack validation: source hash, eight NOS, 119 PCs, task budgets, rubric and links passed.
- Source traceability: identifiers, source pages, coverage, declaration contract and safety text passed.
- Matcher structural checks: 17 passed.
- Python golden vectors: 100 reproduced exactly.
- English/Hindi resources: parity and nonempty-string checks passed.
- Isolated Android QA build: debug application and instrumentation APK built successfully.
- USB capture driver: completed successfully twice on the connected OnePlus 13R. These are repeated runs of one capture driver, not two independent test cases.
- Real local browser flow: protected media, a saved score, a reassessment dialog, report issuance, PDF digest match and anonymous verification completed with no JavaScript page errors.

The browser used a disposable SQLite database and sample media. It does not demonstrate PostgreSQL locking, production load, authenticity of a candidate's work, or a field assessment. [Capture manifest](../assets/readme/capture-manifest.json).

The full backend regression, full Android regression, and current cloud release pipelines were not rerun as part of this documentation task. The live landing page was captured read-only. API health returned `status=ok`, `database=ok`, and `storage=ok`; API and worker source stamps agreed at the time of capture. Health is a point-in-time observation.

## Open validation and implementation items

- The pack marks one generator-maintenance criterion N/A; the current scoring workspace still includes 71 rubric rows. Applicability must be reconciled across UI, scoring, denominators and reports.
- Mapping configuration uses a heuristic safety weight that differs from the official NOS credit. Its labeling/versioning needs a deliberate decision.
- Public-dashboard assessor registration does not verify professional competence or contact ownership. A sensitive pilot needs approved assessors and scoped assignments.
- Independent worker usability, trade-expert agreement, held-out quality/hand evaluation, and entry/mid-tier device targets remain unproven.
- The synthetic statistics harness does not establish improved agreement among real assessors.
- Historical hosted and APK release runs have different outcomes. Inspect the relevant current workflow and artifact receipt before describing release delivery as verified.

The newer implementation and [universal report evidence](../evidence/UNIVERSAL_SIGNED_REPORTS_20261019.md) take priority over older statements that rejection does not issue a signed report. The current UI and API, rather than older module README introductions, describe the present dashboard presentation and password-account behavior.
