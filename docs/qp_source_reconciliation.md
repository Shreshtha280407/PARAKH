# QP source reconciliation — CON/Q0602 Assistant Electrician

## The single pinned source

P1, and every phase built on top of it, uses exactly one file as the source
of truth for CON/Q0602:

- **Local path:** `packs/ae-con-q0602/qp_v4.0.pdf`
- **SHA-256:** `27ef7dc3dfdcaad536bee7c1ebd73fcf7cb381e570f009cbb1b39f1060e514ad`
- **Origin:** `https://s3.ap-south-1.amazonaws.com/nsdcproddocuments/qpPdf/CON_Q0602_v4.0.pdf`
- **Recorded in:** `packs/ae-con-q0602/source.json`

Every NOS code, PC id, PC text, mark, and credit value in `qp.json`,
`tasks.json`, `rubric.json`, and `packs/ae-con-q0602/mapping/*.json` is
transcribed verbatim from this one file. `tools/audit_qp_traceability.py`
checks this mechanically (QP code/version match, every PC carries a
`source_page`/`source_reference` pointing back into this PDF).

## Why the public record can look different, and why that's not a bug here

A web search for "CON/Q0602 Assistant Electrician" turns up several distinct,
publicly hosted PDFs, for example (non-exhaustive, found 2026-10-09):

| Document | Type | Version seen |
|---|---|---|
| `MC_Assistant-Electrician.pdf` (skillmissionbihar.org) | Model Curriculum | unspecified |
| `MCAssistant Electrician v 4.0 CONQ0602.pdf` (skillmissionbihar.org) | Model Curriculum | v4.0 |
| `AG_Assistant-Electrician.pdf` (csdcindia.org) | Assessment Guide | unspecified |
| `CON-Q0602.pdf` (csdcindia.org, 2025-09) | Model Curriculum | unspecified |
| `MC-CON-Q0602_-Assistant-Electrician.pdf` (csdcindia.org, 2022-07) | Model Curriculum | older |
| `PWD_CON_Q0602_v2.0.pdf` (scpwd.in) | Qualification Pack, PWD-adapted | v2.0 |
| `PHB_English_Assistant Electrician_CONQ0602_v3.0.pdf` (scpwd.in) | Divyangjan handbook | v3.0 |
| `FG_English_Assistant-Electrician_CONQ0602_v3.0.pdf` (csdcindia.org) | Facilitator Guide | v3.0 |

None of these are the file pinned in `source.json`. This is expected, not a
discrepancy to reconcile:

1. **Different document types.** A Model Curriculum, an Assessment Guide, a
   Facilitator Guide, and a PWD/Divyangjan adaptation are companion
   documents to a Qualification Pack, not substitutes for it. They can
   restate PC text with different wording, different numbering, or
   additional accessibility-specific criteria. P1 only reads from the
   **Qualification Pack** document type, which is what `qp_v4.0.pdf` is
   (title page: "Qualification Pack", NSQC-approved).
2. **Different versions.** v2.0 and v3.0 PDFs are older revisions of the
   same QP code, superseded by v4.0 (NSQC approval date 2025-05-08, next
   review 2028-04-30, per `qp_v4.0.pdf` page 4). PC wording, PC counts, and
   NOS versions do change between revisions — compare v4.0's CON/N0602
   having 11 PCs against whatever an older version states; they are not
   expected to match, and no attempt is made to reconcile them here.
3. **The NQR portal itself can show a different "current" entry** than the
   PDF snapshot pinned here, because the register is a live system while
   this pack is a point-in-time pin. `source.json.nqr_reference` records
   which NQR entry (`QG-03-CO-03951-2025-V2-CSDCI`) this PDF corresponds to,
   so a future reconciliation has a concrete anchor — but P1 does not poll
   or re-sync against the live NQR portal.

## The rule this document exists to state plainly

**P1 does not merge PC text, marks, NOS codes, or match/rubric thresholds
across these sources.** If a future reviewer (trade expert, SSC auditor, or
engineer) finds that some other Assistant Electrician document phrases a PC
differently, numbers it differently, or assigns it different marks, that is
not evidence of an error in this pack — it is evidence of a different
document. The only actionable finding against *this* pack is a mismatch
against `qp_v4.0.pdf` itself, checked PC-by-PC via `source_page` /
`source_reference` (see `docs/qp_traceability_report.md`).

If CSDCI publishes a new version of CON/Q0602 (v5.0+), the correct response
is a **new pinned pack** (new PDF, new recorded SHA-256, a new pack/rubric
version id) — never an in-place edit that blends old and new text under the
same `source.json` hash.

## Non-QP thresholds: a related but separate caution

`packs/ae-con-q0602/mapping/thresholds.json`'s 0.60 / 0.35 declaration-match
coverage bands are **not** sourced from `qp_v4.0.pdf` at all — the QP does
not define a self-declaration matching heuristic, because self-declaration
matching is an MVP feature of this project, not an NQR/CSDCI concept. They
must never be cited as if CSDCI or NQR had published a pass threshold. See
`packs/ae-con-q0602/mapping/thresholds.json.mvp_disclaimer` for the
machine-readable version of this same caution.
