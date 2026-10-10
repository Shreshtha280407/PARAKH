# QP traceability report — CON/Q0602 v4.0

Generated from `tools/audit_qp_traceability.py packs/ae-con-q0602`. Initial
run 2026-10-09 (P1); re-run 2026-10-10 for Q-1 completion after adding the
`[decl]` check and the match-rules@r2 safety/teamwork/planning declaration
cards; re-run again 2026-10-11 after the r2→r3 declaration-contract
reduction (20 cards + 6 tools) added the `[contract]` and `[safety]` checks
(see `docs/qp/CON_Q0602_v4_source_of_truth.md` and `docs/gates/Q1.md`).
Regenerate this file by re-running that command whenever `qp.json`,
`tasks.json`, `rubric.json`, or `mapping/*.json` change.

## Pinned source

| Field | Value |
|---|---|
| QP code | `CON/Q0602` |
| QP version | `4.0` |
| Sector body | Construction Skill Development Council of India (CSDCI) |
| NSQF level | 3 |
| Local PDF | `packs/ae-con-q0602/qp_v4.0.pdf` |
| SHA-256 | `27ef7dc3dfdcaad536bee7c1ebd73fcf7cb381e570f009cbb1b39f1060e514ad` |
| Recorded in | `packs/ae-con-q0602/source.json` |

See `docs/qp_source_reconciliation.md` for why other publicly hosted
Assistant Electrician documents (different versions, different document
types) are deliberately not consulted here.

## Audit result

```
$ python tools/audit_qp_traceability.py packs/ae-con-q0602
[source] qp_code/qp_version match source.json across 6 files ✓
[nos]    all 8 required NOS present, none extra ✓
[pcids]  no duplicate PC ids across 119 PCs ✓
[text]   every PC has non-empty text ✓
[pages]  source_page + source_reference present on all 8 NOS and 119 PCs ✓
[refs]   every tasks/rubric/mapping PC reference resolves to a real PC ✓
[coverage] coverage_matrix.json matches qp.json/tasks.json, 0 PCs NOT_ASSESSED_IN_MVP, mvp_applicability correct for 1 NOT_APPLICABLE_IN_MVP PC(s) ✓ (TASK_EVIDENCE_PATHWAY=71, DECLARATION_OR_ASSESSOR_NOTE=48)
[decl]   every scored NOS (5) has >= 1 declaration card/tool link ✓
[contract] exactly 20 cards + 6 tools, no duplicate ids, no CON/N8001/CON/N8002 links ✓
[safety] all 5 tasks start with the safety_first_step verbatim, no unsafe phrase present ✓
```

All 10 checks pass, exit 0. `[coverage]` and `[decl]` were added after the
initial P1 run (`[decl]` specifically at Q-1 completion, to make the kind
of gap it would have caught — CON/N9001 having zero declaration cards
under match-rules@r1 — fail CI instead of silently shipping). `[contract]`
and `[safety]` were added at the r2→r3 declaration-contract reduction, to
make a future accidental growth past 20 cards + 6 tools, or a reintroduced
unsafe task-wording phrase, fail CI the same way.

## NOS → source page map

Every PC's `source_page` was set from a direct re-read of the rendered PDF
page (not from memory/OCR-only extraction) — see the page-boundary
verification pass that preceded this file in the build log, which re-opened
pages 9-10, 20-21, 26-27 and 36 specifically because a NOS's PC list splits
across a page break there and a one-PC error was plausible.

| NOS | Title | PCs | Source pages | Practical (task-evidenced)? |
|---|---|---:|---|---|
| CON/N0602 | Handle hand and power tools relevant to construction electrical works | 11 | p.5 | Yes — T2 |
| CON/N0603 | Install temporary lighting arrangement at construction sites | 16 | pp.9-10 | Yes — T4 |
| CON/N0604 | Assist in LV (Low Voltage) electrical wiring at permanent structures | 11 | p.15 | Yes — T3 |
| CON/N0605 | Assemble, install and maintain temporary LV electrical panels (distribution boards) at construction site | 16 | pp.20-21 | Yes — T5 |
| CON/N9001 | Work according to personal health, safety and environment protocols at construction site | 17 | pp.26-27 | Yes — T1 |
| CON/N8001 | Work effectively in a team to deliver desired results at the workplace | 12 | p.32 | No — declaration/assessor-note only |
| CON/N8002 | Plan and organize work to meet expected outcomes | 15 | p.36 | No — declaration/assessor-note only |
| DGT/VSQ/N0101 | Employability Skills (30 Hours) | 21 | pp.41-42 | No — declaration/assessor-note only |
| **Total** | | **119** | | 5 of 8 NOS practical (71 of 119 PCs) |

Each NOS's `nos_parameters_page` (the official "NOS Parameters" table
confirming code/credits/version — pp.8,14,19,25,31,35,40,45 respectively) is
also recorded in `qp.json` alongside the PC-list `source_page`, as a second,
independent page anchor per NOS.

## What "traceable" means here, concretely

For any PC in `qp.json`, e.g. `CON/N0604.PC9`:

```json
{
  "id": "PC9",
  "text": "carry out termination of cables safely as per instruction",
  "source_page": 15,
  "source_reference": "packs/ae-con-q0602/qp_v4.0.pdf p.15, CON/N0604.PC9"
}
```

— a reviewer can open `qp_v4.0.pdf` to page 15 and find that exact sentence
under `CON/N0604`'s "Elements and Performance Criteria" heading, PC9. This
is mechanically checked for all 119 PCs (`[pages]` check); it is **not**
independently re-verified against the PDF text by machine (OCR/text-diff is
out of scope for P1 — see `docs/gates/P1.md` for the human spot-check that
covers that gap).

## Reference integrity (tasks.json / rubric.json / mapping/links.json)

`[refs]` confirms every PC id mentioned outside `qp.json` resolves to a real
`qp.json` PC:

- `tasks.json`: every `linked_pcs` entry across T1-T5
- `rubric.json`: every `items[].pc_id`
- `mapping/links.json`: every `cards[].links[]` / `tools[].links[]` `{nos,pc}` pair

This is the check that would catch a typo'd PC id (e.g. `CON/N0604.PC12`,
which doesn't exist — N0604 only has 11 PCs) silently floating in a rubric
or task file with no connection back to the source QP.
