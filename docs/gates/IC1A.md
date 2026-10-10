# IC-1A — Technical & Standards-Traceability Acceptance

## Why this document exists, and why it replaces the earlier IC-1 wording

The master plan's original IC-1 gate ("17 Oct — Single-QP matcher v1")
read: *"on 60 labelled worker declarations the match result agrees with the
expert's label ... on ≥ 90%."* That is an **independent assessor-agreement
study** — real field-collected declarations, labelled by a trade expert
against candidates' actual interview/experience, compared against the
matcher's output.

**That study was not performed and is not claimed anywhere in this
repository.** No independent reviewer was used. This is a decision made by
the project owner for the Q-1/P-3 scope, not an oversight: a 2-person AI
team building a deterministic rules engine and an offline Android client in
days, with no trade-expert availability and no field-collected worker
sample, cannot honestly produce a 60-declaration expert-agreement number —
any such number would either be fabricated or computed against synthetic
data mislabelled as real validation. `ml/mapping/data/labelled_60.jsonl`
exists and is useful (a smoke test — does the matcher run without errors,
does it behave sanely on a few distinct archetypes), but it is synthetic,
clearly marked as such (`HARNESS_ONLY_NOT_FIELD_VALIDATION`), and
`ml/mapping/eval.py` mechanically refuses to report an agreement
PASS/FAIL against it (see "Honest internal validation data" in
`docs/gates/Q1.md`).

**IC-1A replaces IC-1's wording with what can be honestly proven at
Q-1/P-3**: that the matcher is deterministic, every rule traces back to the
pinned QP PDF, the Kotlin and Python implementations agree exactly, the
whole thing is covered by automated tests, and the Android app runs the
whole worker flow offline. IC-1A proves **technical correctness and
standards traceability**. It does not and cannot prove **assessor
agreement** — that is explicitly out of scope and is named here as a real,
open gap for a later pilot/study phase, not something this document
pretends to have closed.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Deterministic rules, not an LLM/trained model | `ml/mapping/matcher.py` and `core:mapping/Matcher.kt` are pure rule evaluation over versioned JSON data (`packs/ae-con-q0602/mapping/*.json`). No model weights, no inference call, anywhere in either implementation. |
| 2 | QP traceability | `tools/audit_qp_traceability.py packs/ae-con-q0602` — 10/10 checks pass, including `[decl]` (every scored NOS has ≥1 declaration signal), `[contract]` (exactly 20 cards + 6 tools, no CON/N8001/CON/N8002 link), and `[safety]` (every task's step_guide starts with the pinned safety sentence verbatim, no unsafe phrase present). `tools/check_android_string_parity.py` — 3/3 checks pass (EN/HI string parity, Android resources match `links.json` 1:1). `docs/qp/CON_Q0602_v4_source_of_truth.md`, `docs/qp_declaration_traceability.md`. |
| 3 | Python/Kotlin parity on all 100 golden vectors | `python3 ml/mapping/test_golden_vectors.py` (Python self-check) and `./gradlew :core:mapping:test --tests "*GoldenVectorsTest*"` (Kotlin vs the same `ml/mapping/golden_vectors.jsonl`) both pass, 100/100, on the 20-card + 6-tool match-rules@r3 contract. See "Exact commands and actual results" below. |
| 4 | Automated tests | 17 Python tests (`ml/mapping/test_matcher.py`) + 1 (`test_golden_vectors.py`, 2 sub-checks) + 13 Kotlin tests (`GoldenVectorsTest` + `MatcherTest`) + 6 Android instrumented test classes, 8 test methods (`docs/gates/P3.md`). |
| 5 | Offline Android execution | `docs/gates/P3.md` — full worker journey (language → consent → registration → declaration → match → tasks → evidence → preview → attestation → local submit) proven on-device with no `INTERNET`/`ACCESS_NETWORK_STATE` permission declared and airplane mode on. |
| 6 | Matcher supports QP relevance only, never certifies competence | `thresholds.json.never_decides_competence`, `thresholds.json.mvp_disclaimer`, `rubric.json.rules.wording_rule` ("No UI, API response, or generated report may use 'certified', 'official pass', or 'official certificate'"). MatchResultScreen (Android) and every Python/Kotlin output field name reflect this (`match_result` ∈ {appropriate/partial/not_appropriate}_match, never a score). |

## Exact commands and actual results

```
$ echo "27ef7dc3dfdcaad536bee7c1ebd73fcf7cb381e570f009cbb1b39f1060e514ad  packs/ae-con-q0602/qp_v4.0.pdf" | sha256sum -c -
packs/ae-con-q0602/qp_v4.0.pdf: OK

$ python3 tools/audit_qp_traceability.py packs/ae-con-q0602
[source] qp_code/qp_version match source.json across 6 files ✓
[nos]    all 8 required NOS present, none extra ✓
[pcids]  no duplicate PC ids across 119 PCs ✓
[text]   every PC has non-empty text ✓
[pages]  source_page + source_reference present on all 8 NOS and 119 PCs ✓
[refs]   every tasks/rubric/mapping PC reference resolves to a real PC ✓
[coverage] coverage_matrix.json matches qp.json/tasks.json, 0 PCs NOT_ASSESSED_IN_MVP, mvp_applicability correct for 1 NOT_APPLICABLE_IN_MVP PC(s) ✓
[decl]   every scored NOS (5) has >= 1 declaration card/tool link ✓
[contract] exactly 20 cards + 6 tools, no duplicate ids, no CON/N8001/CON/N8002 links ✓
[safety] all 5 tasks start with the safety_first_step verbatim, no unsafe phrase present ✓

$ python3 tools/check_android_string_parity.py
[parity]   values/ and values-hi/ define the same string names across 3 files ✓
[nonempty] all 262 string values (both locales) are non-empty ✓
[contract] card_labels.xml (both locales) has exactly one label per links.json id (26 ids) ✓

$ python3 ml/mapping/test_matcher.py
ml/mapping/test_matcher.py: all 17 checks passed

$ python3 ml/mapping/test_golden_vectors.py
ml/mapping/test_golden_vectors.py: all 100 golden vectors reproduce exactly, matcher is deterministic

$ cd apps/android && ./gradlew :core:mapping:test --rerun-tasks --console=plain
GoldenVectorsTest: all_100_vectors_match_python PASSED
GoldenVectorsTest: matcher_is_deterministic PASSED
GoldenVectorsTest: no_network_mode_does_not_affect_matching_or_task_pack_loading PASSED
MatcherTest: 10/10 PASSED
BUILD SUCCESSFUL -- 13 tests completed, 0 failed

$ ./gradlew :app:assembleDebug :app:lintDebug :app:connectedDebugAndroidTest --console=plain
BUILD SUCCESSFUL -- 8/8 instrumented tests pass on KaushalPramaan_API35 (API 35)
```

(Full real transcripts, including the Android instrumented E2E run on
`KaushalPramaan_API35`, are in `docs/gates/Q1.md` and `docs/gates/P3.md`;
this table exists to state the IC-1A acceptance decision in one place.)

## A genuine finding this process surfaced

Building the Kotlin port for criterion 3 surfaced a real Python/Kotlin
float-summation discrepancy (CPython's `sum()` compensated-summation
behaviour vs Kotlin stdlib's naive summation, flipping a value at an exact
4-decimal rounding boundary) — not a cosmetic porting difference but a case
where the two "identical" rule engines would have silently disagreed on a
live declaration landing on that boundary. It is fixed (see
`docs/gates/Q1.md`'s "A real cross-language float-summation bug" section)
and is recorded here as evidence that the parity requirement did real work,
not just a formality.

## Limits, stated honestly

- **No independent assessor-agreement study was performed.** Outside the
  approved technical IC-1A scope; not claimed as completed. A real study
  needs: field-collected declarations from real candidates, a trade expert
  to label each one against the candidate's actual interview/experience
  (without the label being circular with the matcher's own formula), and a
  dataset saved without any synthetic-data marker. None of that exists yet.
- **No human usability study was performed for the Android app, in Hindi or
  English.** `HindiFlowTest` (`docs/gates/P3.md`) is an automated UI test
  only — it asserts that Hindi strings render and the scripted flow
  completes, not that an independent non-team person completed it unaided.
  Outside the approved technical IC-1A scope; not claimed as completed.
- **No certification claim is made anywhere.** The matcher routes a
  self-declaration to appropriate / partial / not-appropriate *for
  assessment against* CON/Q0602 — nothing more. The human assessor remains
  the only party who can decide competence, and P-3's Android app never
  shows "certified," "qualified," "passed," or "failed."
- **The 0.60/0.35 coverage bands are MVP heuristics**, not NQR/CSDCI
  thresholds (`thresholds.json.mvp_disclaimer`).
- **This gate covers Q-1 and P-3 only.** It says nothing about P-4+ (real
  capture, Room, encryption, sync, server-side scoring) — outside the
  approved technical IC-1A scope; not claimed as completed here.

## Status

**IC-1A: PASSED** for the criteria it actually defines (table above).
Independent assessor-agreement validation remains unperformed and
unclaimed, explicitly, by design.
