# Safety boundaries — CON/Q0602 Assistant Electrician pilot

These boundaries are referenced from `packs/ae-con-q0602/` (the task guides, the
rubric's critical PCs) and from the capture flow in the worker app. They are
not optional per-phase guidance — every phase that touches evidence capture,
the rubric, or the dashboard must uphold them.

## 1. De-energised training board only

All five practical tasks (T1-T5) are performed on a **de-energised training
board**, or under direct on-site supervision for any task that momentarily
needs live verification (e.g. a continuity check after isolation). The app
never instructs live work, and no task guide in `tasks.json` asks a worker to
work on an energised circuit.

Training board kit (per the master plan's P1 blocker checklist): switch,
socket, MCB, small distribution board, lamp holder, wires, voltage tester,
multimeter.

## 2. Isolation and tester-check first

Every task guide in `tasks.json` that involves touching a conductor starts
with an isolation and/or tester-check step (see T1's dedicated PPE +
isolation task, and the isolation/tester steps embedded in T3, T4, T5).
Skipping this step is visible to the assessor in the evidence and drives the
critical safety PCs in `rubric.json` (every PC under CON/N9001 is `critical:
true`, along with the specific live-work safety PCs called out in other NOS —
see `rubric.json.rules.critical_pc`). A critical PC scored below level 2 means
that NOS cannot be marked competent, regardless of the overall NOS score.

## 3. No biometric processing, no face requirement

Faces are not required in evidence. Workers are told to frame their hands and
the work, not their face. The MVP does not do face liveness, face matching,
PAD, or duplicate-face search (see the master plan's "What changed from the
Master Design document" table — these were explicitly removed for the MVP: no
biometric consent flow exists, so no biometric capture is permitted).

## 4. Output wording

Every user-facing surface (worker app, dashboard, PDF report) must say
**"NSQF-aligned competency profile and assessor recommendation"** — never
*"certificate"*, *"pass"*, or *"fail"*. The signed PDF report footer states:
*"Assessor recommendation — not an official certificate."* Official
certificates remain the awarding body's (CSDCI's) role, not this tool's.

## 5. AI never decides competence

Any on-device or server-side AI assistance (quality flags, hands-visible
flags, optional tool/PPE detection) may only warn, flag, or mark where to
look. It never outputs pass/fail/certified, never sets or pre-fills a PC
score, and never blocks a submission. See `packs/ae-con-q0602/mapping/thresholds.json
.never_decides_competence` for the same rule applied to the declaration
matcher specifically: the matcher explains how a declaration relates to the
QP, it does not decide competence.
