# P1 Technical Completion Report — CON/Q0602 QP, task pack, match rules & rubric

Date: 2026-10-09. Scope: master plan §8 P1, extended by this audit to make
P1 100% technically complete and traceable to the pinned official QP.
Nothing in this report is committed or pushed — see "Nothing committed"
below and the `git status`/`git diff` at the end of this message.

## 1. Source hash — verified

```
$ sha256sum packs/ae-con-q0602/qp_v4.0.pdf
27ef7dc3dfdcaad536bee7c1ebd73fcf7cb381e570f009cbb1b39f1060e514ad  packs/ae-con-q0602/qp_v4.0.pdf
```

Matches the required hash exactly. Recorded in
`packs/ae-con-q0602/source.json` (origin URL, local path, NSQF level, sector
body, download date, canonical-source note, and an explicit "do not mix"
list). `docs/qp_source_reconciliation.md` documents 8 other publicly hosted
Assistant Electrician documents found during sourcing (older QP versions,
Model Curricula, Assessment/Facilitator Guides) and states plainly that none
of them were consulted for any field in this pack.

## 2. QP data coverage

| Metric | Value |
|---|---|
| NOS | 8 (all compulsory NOS of CON/Q0602 v4.0) |
| Total PCs | 119 |
| PCs with `source_page` + `source_reference` | 119 / 119 |
| Practical (task-evidenced) NOS | 5 — CON/N9001, CON/N0602, CON/N0603, CON/N0604, CON/N0605 |
| Declaration-only NOS | 3 — CON/N8001, CON/N8002, DGT/VSQ/N0101 |
| Duplicate PC ids | 0 |
| Empty PC text fields | 0 |
| Unresolved PC references (tasks/rubric/mapping) | 0 |

## 3. Coverage-by-evidence-status counts

From `packs/ae-con-q0602/coverage_matrix.json` (also available as `.csv`):

| Status | Count | Meaning |
|---|---:|---|
| `DIRECT_TASK_EVIDENCE` | 71 | PC is in >=1 of T1-T5's `linked_pcs`; scored 0-3 against `rubric.json` anchors from captured evidence |
| `DECLARATION_OR_ASSESSOR_NOTE` | 48 | PC belongs to N8001/N8002/N0101; self-declaration + up to 3 assessor questions only, no task capture, no 0-3 score |
| `NOT_ASSESSED_IN_MVP` | 0 | Must be zero for this pack — `tools/audit_qp_traceability.py`'s `[coverage]` check fails the build otherwise |

71 + 48 = 119. The fixed five task bundles (T1 Safety, T2 Tools/Meter, T3 LV
Wiring, T4 Temporary Lighting/Fault, T5 Temporary LV Panel) are unchanged —
no top-10 task choice, no worker-selected substitution, no alternative-task
path exists anywhere in `tasks.json` or the validators.

## 4. Checks passed (exhaustive list)

**`tools/pack_validate.py packs/ae-con-q0602`** — 5/5 checks: `[qp]` `[tasks]`
`[rubric]` `[links]` `[match]`.

**`tools/audit_qp_traceability.py packs/ae-con-q0602`** (new in this audit)
— 7/7 checks: `[source]` `[nos]` `[pcids]` `[text]` `[pages]` `[refs]`
`[coverage]`.

**`ml/mapping/eval.py --rules packs/ae-con-q0602/mapping --set
ml/mapping/data/labelled_60.jsonl`** — 0 errors across 60 declarations
(exceeds the 20-record P1 gate); harness banner printed; no IC-1 verdict
claimed (structurally impossible in `--mode harness`).

**`ml/mapping/test_matcher.py`** — 4/4 structural self-checks.

**`ml/mapping/test_golden_vectors.py`** (new in this audit) — 100/100
golden vectors reproduce exactly; matcher confirmed deterministic.

**5 negative fixtures, each failing only its one targeted check:**

| Fixture / command | Defect | Fails |
|---|---|---|
| `tests/fixtures/pack_121mb` | Task budgets sum to 121 MB | `pack_validate.py` `[tasks]` |
| `tests/fixtures/pack_missing_pc_task` | Practical PC with no task reference | `pack_validate.py` `[links]` + `audit_qp_traceability.py` `[coverage]` |
| `tests/fixtures/pack_wrong_qp_version` | `qp.json` version drifts from `source.json` | `audit_qp_traceability.py` `[source]` |
| `tests/fixtures/pack_unknown_pc_ref` | Nonexistent PC id referenced from a task | `audit_qp_traceability.py` `[refs]` |
| `eval.py --mode field` against `labelled_60.jsonl` | Attempt to claim synthetic data as field validation | refuses to run, exit 1 |

Full transcripts for every command above are reproduced verbatim at the end
of this conversation turn, immediately after `git diff`/`git status`.

## 5. Wording audit

Repo-wide case-insensitive grep for `certified`, `official pass`, `official
certificate`, `certificate`, `pass`, `fail` across `packs/ apps/ server/ ml/
tools/ docs/ tests/` (excluding the pinned PDF). Every hit is one of:

- Verbatim QP text that cannot be reworded without breaking traceability
  (e.g. PC12 of N9001: *"obtain 'height pass' clearance for working at
  heights"*).
- An explicit disclaimer reinforcing the correct wording (e.g.
  `thresholds.json.mvp_disclaimer`, `rubric.json.rules.output_contract.wording_rule`,
  `docs/safety.md` section 4).
- Developer tooling output (`pack_validate.py`/`audit_qp_traceability.py`
  printing `"n check(s) failed"` to a terminal — not user-facing product
  copy).

No occurrence of "certified", "official pass", or "official certificate" as
a product claim exists anywhere in the repo. `docs/safety.md` and
`rubric.json.rules.output_contract` both fix the required wording:
**"NSQF-aligned competency profile and assessor recommendation."**

## 6. Known MVP limitations (stated openly, not hidden)

1. `ml/mapping/data/labelled_60.jsonl` is synthetic (three archetypes,
   labels assigned independently of the matcher formula). Structurally
   marked `HARNESS_ONLY_NOT_FIELD_VALIDATION` on every record and enforced
   by `eval.py`'s `--mode harness`/`--mode field` split — not just
   documented, but mechanically un-mixable with real field data.
2. The 0.60/0.35 declaration-match coverage thresholds are MVP heuristics
   invented for this project. CON/Q0602 v4.0 defines no self-declaration
   matching concept at all; its own (unrelated) pass rule is a 50% aggregate
   for a full formal assessment. `thresholds.json.mvp_disclaimer` states
   this explicitly.
3. `rubric.json` is explicitly labelled, per item, `"MVP assessor-support
   rubric; not an official SSC scoring replacement."` Per-PC marks are an
   equal split of each element's official marks (the QP publishes marks per
   element, not per PC) — flagged for trade-expert review.
4. `CON/N0603.PC16` (diesel generator preventive maintenance) has a task
   reference (T4) but no real capture step — there is no generator on the
   training board kit. `coverage_matrix.json` carries an explicit `caveat`
   on this one row so it is never mistaken for real evidence.
5. CON/N8001, CON/N8002, DGT/VSQ/N0101 (teamwork, planning, employability)
   get declaration + assessor-note coverage only — an honest, stated MVP
   limitation (master plan's own scope decision), not a fabricated practical
   pass.
6. The Python/Kotlin golden-vector parity requirement is only half-built:
   the Python side (`golden_vectors.jsonl` + `test_golden_vectors.py`,
   100 vectors) exists and is green; the Kotlin matcher port is P3 scope and
   does not exist in this repo yet.

## 7. Remaining pilot-validation work (does not block P2/P3)

- Trade-expert review of 10 rubric anchors (list in `docs/gates/P1.md`) and
  sign-off.
- Trade-expert review of `mapping/links.json`'s 27 declaration cards + 8
  tools against real informal-electrician self-description patterns.
- Field collection of real, expert-labelled worker declarations, saved
  **without** a `harness_marker` field, to run
  `eval.py --rules ... --set <real_data>.jsonl --mode field` for the actual
  IC-1 >=90% agreement gate.
- Kotlin port of `matcher.py` (P3) checked against `golden_vectors.jsonl`.
- Independent re-check of the 10-PC verbatim-match spot-check already done
  by the implementer (`docs/gates/P1.md`), by someone who did not build this
  phase.

None of the above blocks starting P2 (backend) or P3 (Android) engineering
work, which build against `qp.json`/`tasks.json`/`rubric.json`/`mapping/*.json`
as data contracts — see `docs/gates/P1.md`'s "Final checklist" section for
the explicit engineering-completion-vs-pilot-readiness split.

## 8. Nothing committed

All changes in this audit are untracked/modified files in the working tree.
No `git add`, `git commit`, or `git push` was run. See `git status` and
`git diff` at the end of this turn.
