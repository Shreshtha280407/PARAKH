# Evidence status model (P1.1 correction)

P1's first pass conflated two different things under one label,
`DIRECT_TASK_EVIDENCE`: "a T1-T5 task exists that is supposed to evidence
this PC" and "this PC was demonstrated." Those are not the same claim — a
task being linked to a PC says nothing about what a specific worker's
specific submitted evidence actually shows. This document is the corrected
model, in two separate axes, and the contract P2's assessment API must
implement on top of it.

## Axis 1 — evidence pathway (pack-design-time, static, same for every assessment)

Lives in `packs/ae-con-q0602/coverage_matrix.json` / `rubric.json`'s
`evidence_pathway` field. Answers: *how can this PC be assessed at all, in
the fixed T1-T5 structure?*

| Pathway | PCs | Meaning |
|---|---:|---|
| `TASK_EVIDENCE_PATHWAY` | 71 | PC is in >=1 of T1-T5's `linked_pcs`. An assessor **may** score it 0-3 from captured evidence — *if* that evidence actually shows it. |
| `DECLARATION_OR_ASSESSOR_NOTE` | 48 | PC belongs to CON/N8001, CON/N8002 or DGT/VSQ/N0101. Self-declaration + up to 3 assessor questions only. Never has a 0-3 score to give or withhold. |
| `NOT_ASSESSED_IN_MVP` | 0 | No pathway exists. Must be empty for the pinned pack — enforced by `tools/audit_qp_traceability.py`'s `[coverage]` check. |

Renamed from `DIRECT_TASK_EVIDENCE` in this P1.1 pass specifically because
the old name read as a claim of proof it never was.

## `mvp_applicability` — a pathway-level override

One PC, `CON/N0603.PC16` ("perform preventive maintenance on diesel
generators..."), carries `mvp_applicability: "NOT_APPLICABLE_IN_MVP"` instead
of the default `"ASSESSABLE"`. It stays on the `TASK_EVIDENCE_PATHWAY` (T4
still lists it in `linked_pcs`, so `[links]`/`[coverage]` keep passing) but
is structurally excluded from scoring: **no training-board kit includes a
diesel generator**, so no amount of good evidence could ever show this PC in
the current MVP. This is a pack-design fact, not a per-assessment judgement
call — every assessment pre-sets this PC's axis-2 outcome to
`NOT_APPLICABLE_IN_MVP` without an assessor ever reviewing evidence for it.
If a future phase adds a real, safe generator task, flip
`mvp_applicability` back to `"ASSESSABLE"` for that PC in both
`coverage_matrix.json` and `rubric.json` — do not repurpose this flag for
any other PC without the same reasoning (equipment genuinely absent, not
"evidence was weak this time," which is axis 2's `NOT_OBSERVABLE`).

`tools/audit_qp_traceability.py`'s `[coverage]` check enforces that exactly
`{CON/N0603.PC16}` carries this flag and no other PC does.

## Axis 2 — assessor outcome (assessment-time, per submission; P2 scope)

**Not yet implemented** — this is the contract P2's `scores` table and
assessment/report API must satisfy once scoring exists. Applies only to
`TASK_EVIDENCE_PATHWAY` PCs with `mvp_applicability: "ASSESSABLE"`; recorded
once per PC per assessment, not once per pack.

| Outcome | Meaning | Scored? |
|---|---|---|
| `DEMONSTRATED` | Assessor reviewed the submitted evidence and it clearly shows this PC. | Yes, 0-3 against `rubric.json` anchors. |
| `NOT_OBSERVABLE` | Evidence was submitted for the linked task, but doesn't show this specific PC (bad angle, skipped step, too short, etc). | No score. Drives a reassessment request (master plan Fig. 5) — this is exactly what that loop exists for. |
| `NOT_APPLICABLE_IN_MVP` | Pre-set from axis-1 `mvp_applicability`. Currently only `CON/N0603.PC16`. | Never scored, never requested for reassessment. |

## The required 4-way API/report distinction

Any profile, report, or API response that lists PC-level results **must**
keep these four categories visibly separate — never collapse any of them
into a single flat score list, and never let the absence of a score read as
a zero:

1. **demonstrated** — axis 2 = `DEMONSTRATED` (has a 0-3 score)
2. **declaration-only** — axis 1 = `DECLARATION_OR_ASSESSOR_NOTE` (no score, ever)
3. **not-observable** — axis 2 = `NOT_OBSERVABLE` (no score yet, evidence insufficient this round)
4. **not-applicable** — axis 2 = `NOT_APPLICABLE_IN_MVP` (no score, structurally excluded)

## Wording, unchanged from P1

Output everywhere stays **"NSQF-aligned competency profile and assessor
recommendation"** — never "certified," "official pass," or "official
certificate." See `docs/safety.md` section 4 and
`rubric.json.rules.output_contract.wording_rule`.

## What did NOT change in this P1.1 pass

Per the explicit scope of this hardening pass: the QP text (`qp.json`), the
fixed five-task structure (T1 Safety, T2 Tools/Meter, T3 LV Wiring, T4
Temporary Lighting/Fault, T5 Temporary LV Panel), task budgets (15+20+30+25+30
= 120 MB), task order, and the matcher's 0.60/0.35 coverage thresholds are
all untouched. Only the evidence-status *labels and model* were corrected.
