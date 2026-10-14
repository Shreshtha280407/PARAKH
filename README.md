# PARAKH
Prior-skill Assessment &amp; Recognition through AI-driven Knowledge

## Phase status

| Phase | Scope | Status | Gate doc |
|---|---|---|---|
| P1 | QP CON/Q0602 pack, task pack, rubric | Complete | `docs/gates/P1.md` |
| P2 / P2.1 / P2.2 | Backend, storage, dashboard, lifecycle, scoring, signed reports, tokens | Complete | `docs/gates/P2_1.md`, `docs/gates/P2_2.md` |
| Q-1 | Single-QP CON/Q0602 deterministic matcher (match-rules@r3, 20 declaration cards + 6 tools), 100 golden vectors, EN/HI/Hinglish, validation | Complete | `docs/gates/Q1.md` |
| P-3 | Offline Android worker flow (Kotlin/Compose) with mock evidence, Kotlin/Python matcher parity | Complete | `docs/gates/P3.md` |
| IC-1A | Technical & standards-traceability acceptance (replaces earlier expert-agreement IC-1 wording) | Passed | `docs/gates/IC1A.md` |
| P-4 | Offline evidence capture (real CameraX photo/video, no mock evidence), SQLCipher-encrypted Room drafts, crash-safe preview/retake/replace/delete, physical-device gate on a real OnePlus 13R | Complete | `docs/gates/P4.md` |
| P-5 | Automatic local photo/video optimisation to fit budget (no bitrate/resolution/quality control exposed to workers), deterministic budget ledger, canonical signed manifest, Android Keystore ECDSA signing, Tink-encrypted local vault, durable Room outbox, crash-safe seal state machine, physical-device gate (incl. live crash recovery) on a real OnePlus 13R | Complete | `docs/gates/P5.md` |
| P-6 | Resumable WorkManager sync of the P5 sealed outbox (1 MiB streamed chunks over HTTPS, server-side ECDSA signature + hash verification, resumable/idempotent protocol), background metadata extraction, assessor review workspace (protected evidence gallery/player, declaration/sync status, audit log) | Complete, incl. physical-device manual gate on a real OnePlus 13R | `docs/gates/P6.md`, `docs/gates/P6_physical_device_2026-10-14.md` |
| P7 | Computed NOS-wise competency profile + recommendation (pinned-pack thresholds, critical-PC rule), assessor override with mandatory server-enforced reason, task-specific reassessment with versioned/resumable recapture (unchanged tasks inherited by reference, never re-uploaded), worker-app reassessment/report-status polling, password-confirmed sign-off, PDF-first detached Ed25519 signing (immutable stored artifact, key-history-aware), public `/verify/{report_id}` + offline `tools/verify_report.py` | Physical-device and live-dashboard run recorded with fixes; completed | `docs/gates/P7.md`, `docs/gates/P7_codex_handoff.md`, `docs/gates/P7_physical_device_2026-10-14.md` |
| P8+ | CV/AI quality analysis, MediaPipe Hands, model training, additional qualification packs/trades, Q2/Q3/Q4 | Outside the approved P-7 scope; not claimed as completed | — |

Independent assessor-agreement validation (the original master-plan IC-1
≥90%-agreement study) was **not performed** and is not claimed anywhere in
this repository — see `docs/gates/IC1A.md` for the honest limitation
statement and what IC-1A proves instead. Likewise, no human usability study
(e.g. an independent non-team person completing the Android flow in Hindi
unaided) was performed — `docs/gates/P3.md`'s `HindiFlowTest` is an
automated UI test only. Both are outside the approved technical IC-1A
scope; not claimed as completed.
