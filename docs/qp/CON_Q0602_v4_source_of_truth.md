# CON/Q0602 v4.0 — pinned source of truth (Q-1 completion record)

## Identity

| Field | Value |
|---|---|
| QP code | `CON/Q0602` |
| QP name | Assistant Electrician |
| Version | **v4.0** |
| Sector body | Construction Skill Development Council of India (CSDCI) |
| NSQF level | 3 |
| NQR reference | `QG-03-CO-03951-2025-V2-CSDCI` |
| NSQC approval date | 2025-05-08 |

## Pinned local source

| Field | Value |
|---|---|
| Local path | `packs/ae-con-q0602/qp_v4.0.pdf` (repo-relative from this file: `../../packs/ae-con-q0602/qp_v4.0.pdf`) |
| SHA-256 | `27ef7dc3dfdcaad536bee7c1ebd73fcf7cb381e570f009cbb1b39f1060e514ad` |
| Verify with | `sha256sum packs/ae-con-q0602/qp_v4.0.pdf` |
| Original download URL | `https://s3.ap-south-1.amazonaws.com/nsdcproddocuments/qpPdf/CON_Q0602_v4.0.pdf` |
| PDF page count | 53 |
| Downloaded on | 2026-10-09 |
| SHA-256 last re-verified | 2026-10-09 (P1) and 2026-10-10 (Q-1 completion, this document) |
| This document generated | 2026-10-10T13:21:58Z |

This record is generated, not hand-maintained prose: `source.json`,
`qp.json`, `tasks.json`, `rubric.json`, and `packs/ae-con-q0602/mapping/*.json`
all carry the same `qp_code`/`qp_version`/`sha256` fields, and
`tools/audit_qp_traceability.py`'s `[source]` check fails the build if any of
them drift from `packs/ae-con-q0602/source.json`, which is the single
machine-readable record this file restates for human readers.

## Statement of provenance

**Every Q-1 rule — every NOS code, PC id, PC text, mark, credit value,
task budget, rubric anchor, and declaration-card/NOS/PC link — derives from
this one pinned PDF, verified by the SHA-256 above, and from no other
source.** This includes:

- `packs/ae-con-q0602/qp.json` (NOS/PC text, verbatim transcription)
- `packs/ae-con-q0602/tasks.json` (T1-T5, evidence budgets, linked PCs)
- `packs/ae-con-q0602/rubric.json` (anchors, marks, critical-PC flags)
- `packs/ae-con-q0602/mapping/links.json` (declaration card/tool → NOS/PC)
- `packs/ae-con-q0602/mapping/keywords.json` (EN/HI/Hinglish free-text terms)
- `packs/ae-con-q0602/mapping/thresholds.json` (match-rules@r3: the 0.60/0.35
  coverage bands and `answer_strength` values are **not** themselves sourced
  from the PDF — they are MVP matching heuristics invented for this project;
  see `thresholds.json.mvp_disclaimer` and
  `docs/qp_source_reconciliation.md` for why that distinction matters)

Other publicly hosted Assistant Electrician documents exist (Model
Curricula, Assessment Guides, Facilitator Guides, older QP versions, a
PWD-adapted handbook) — none of them are consulted here, by design. See
`docs/qp_source_reconciliation.md` for the full reconciliation and why a
different wording/numbering in one of those documents is not evidence of an
error in this pack.

## Version-change rule

**Silent replacement is never allowed.** If CSDCI publishes CON/Q0602 v5.0
(or any later version):

1. The new PDF is downloaded, hashed, and stored as a **new** file (e.g.
   `packs/ae-con-q0602/qp_v5.0.pdf`), never overwriting `qp_v4.0.pdf`.
2. A documented diff is produced: which NOS/PC/text/marks/credits changed
   versus v4.0, written up before any rule file changes.
3. Every rule file that encodes v4.0 data gets a **new pack/rubric/rules
   version id** (e.g. `rubric_id: "ae-con-q0602@v5.0-r1"`,
   `match_rules_id: "match-rules@r3-v5"` or similar) — never an in-place
   edit that blends v4.0 and v5.0 data under the same version id.
4. `source.json`'s `sha256` is updated only as part of that same versioned
   change, together with every file `tools/audit_qp_traceability.py`'s
   `[source]` check inspects — so the CI gate fails loudly if a future
   change updates the PDF pointer without updating everything that depends
   on it.

This mirrors the same rule already stated for the rules engine itself: see
`packs/ae-con-q0602/mapping/thresholds.json.status` (r1 → r2 at Q-1
completion was exactly this kind of versioned change, not an in-place edit
of r1's meaning — CON/N9001 was added to `practical_nos_for_matching`
rather than silently changing what r1 claimed to compute).

## Related documents

- `docs/qp_source_reconciliation.md` — why the public record can show
  different Assistant Electrician documents without that being a
  discrepancy to "fix" here.
- `docs/qp_traceability_report.md` — the generated NOS→page audit report
  (`tools/audit_qp_traceability.py` output).
- `docs/qp_declaration_traceability.md` — the full declaration item → NOS →
  PC → task → weight → reason-code map.
- `docs/gates/Q1.md` — Q-1 completion gate (commands, expected output, pass
  criteria).
- `docs/gates/IC1A.md` — the technical & standards-traceability acceptance
  gate that replaces the former expert-agreement IC-1 wording for Q-1/P-3.
