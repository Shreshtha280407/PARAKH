# D3 synthetic assessment engineering validation

**This report uses synthetic packages, synthetic reference scores and simulated raters. It validates the software and statistics only. It is not evidence of agreement improvement among real assessors.**

MVP assessor-support rubric; not an official SSC scoring replacement. The pinned
rubric remains **draft — pending trade-expert sign-off**. No real assessors
participated, no expert gold was collected, and original physical D3/D5 study
requirements remain unfulfilled. The owner-amended scope replaces D3 collection
with this engineering fixture and skips D5, D1/D2/D4 and optional P9.

## Audit and source grounding

Implementation started from clean `main` at
`7e18d6e24c7dbc7cb111625f73fee16b7d0546ff`. The local master-plan PDF was absent;
the owner requirements and versioned project contracts govern this reduced D3.
Audited inputs include `packs/ae-con-q0602/{qp,rubric,tasks,coverage_matrix}.json`,
`server/app/{outcome,models,schemas}.py`, assessment/scoring routers, the existing
dashboard assessment-detail page, P1/P7/P8/Q4 gates, evidence-status contract,
prior integration evidence, generators, Python tests and GitHub Actions.

CON/Q0602 v4.0 has eight NOS and 119 PCs. Five task-evidenced NOS provide 71 rubric
items, including one structurally not-applicable PC (`CON/N0603.PC16`). Therefore
70 distinct PCs can receive levels. The other 48 PCs are declaration/notes only.
All task titles/mappings, marks, critical flags, applicability and anchors come
from those files. We preserve the current equal-split MVP marks and threshold
rules; no official SSC scoring scheme is inferred.

## Reproduce offline

The pipeline itself uses **only Python's standard library** and imports the pure
production outcome function; it imports no server configuration, database or HTTP
application. Python 3.12–3.14 is supported. From the repository root:

```sh
# Rebuild dataset, validate/regenerate it and produce the full 2000-draw report.
python ml/study/reproduce.py

# Verify all five data artifacts and three report artifacts in a temporary
# directory. This command does not overwrite the canonical artifacts.
python ml/study/reproduce.py --check
```

Individual commands, including the requested seed/count interface:

```sh
python ml/study/generate_demo_data.py --seed 42 --count 20 --out-dir ml/study/data
python ml/study/simulate_ratings.py --seed 42 --policy baseline \
  --reference ml/study/data/expected_pc_levels.csv
python ml/study/validate_dataset.py --check-reproducible
python ml/study/agreement.py ml/study/data/simulated_ratings.csv \
  --reference ml/study/data/expected_pc_levels.csv \
  --bootstrap 2000 --seed 42 --out ml/study/reports/synthetic_validation.md
```

Choose a separate `--out-dir /tmp/d3-custom/data` for another seed/count, then pass
those paths to the simulator, validator and analysis. Counts must be positive
multiples of four to maintain balanced scenarios. Canonical fixtures use exactly
20 packages. Generator/simulator write only their designated study artifacts.
Use a separate output directory when retaining an earlier experiment. No tool
loads synthetic records into a production database.

Independent numerical oracles are test dependencies, isolated from production:

```sh
python -m venv /tmp/parakh-d3-venv
/tmp/parakh-d3-venv/bin/python -m pip install -r ml/study/requirements-test.txt
/tmp/parakh-d3-venv/bin/python -m pytest ml/study/tests -q
```

The pinned file includes transitive dependencies. Once installed, tests and the
entire pipeline run offline. No ML training, inference service or media access
is required. GitHub Actions adds an independent D3 job; all earlier jobs remain.

## Artifact contracts (schema version 1)

Executable validation lives in `common.py` and `validate_dataset.py`; unknown
columns/fields in generated records, missing identities, duplicate rows,
incorrect pack metadata and provenance drift fail validation. The generic
analysis reader permits extra CSV metadata and explicit incomplete cohorts so
it can audit exclusions; canonical dataset validation requires the complete
expected roster. UTF-8, LF endings, stable ordering, explicit seeds, content
hashes and no wall clock/UUIDs make canonical regeneration byte-identical.

| Artifact | Identity and content | P10 use |
|---|---|---|
| `data/packages.jsonl` | One object per `SIM-001`…`SIM-020`; QP/rubric identifiers and disclaimer; scenario, fictional declaration, five pack-derived task references, all 119 PC statuses/expected levels, critical flags and engine-derived expected recommendation | Scenario selection and stable assessment references |
| `data/expected_pc_levels.csv` | Unique `(package,pc)`; `nos,task,evidence_status,level,scenario,marks,critical,evidence_pathway,mvp_applicability,anchors_json,ambiguity,reference_kind,synthetic` | Controlled reference values and rubric provenance |
| `data/simulated_ratings.csv` | Unique `(package,pc,rater,condition)`; `nos,task,evidence_status,level,scenario,simulation_seed,policy,synthetic`; three raters in both conditions | Manual/assisted comparison input, filtered by `condition` |
| `data/evidence_manifest.jsonl` | Unique `evidence_id`, linked package/task; photo/video kind, fictional availability/quality, expected per-PC status relationship and synthetic provenance | Metadata-only study tooling fixtures |
| `data/dataset_manifest.json` | Generator/schema version, seeds, scenario counts, simulation policy/parameters/roster, source/artifact SHA-256 | Provenance gate before a demo |
| `reports/dataset_validation.md` | Actual counts, missingness, score distributions, critical scenarios, sources and regeneration result | Dataset QA evidence |
| `reports/synthetic_validation.{md,json}` | Actual metrics, pairwise QWK, differences, CIs, undefined reasons and exhaustive cohort audit | Human-readable demonstration and machine-readable study results |

The rubric's version identifier is its full `rubric_id`,
`ae-con-q0602@v4.0-r1`, matching production `RubricItem.rubric_version`.
No separate rubric version is invented.

Evidence status has four distinct meanings:

| Status | `level` | Interpretation |
|---|---|---|
| `DEMONSTRATED` | Integer 0–3 | Controlled observable scenario outcome; zero is observed deficient performance |
| `NOT_OBSERVABLE` | Blank CSV / JSON null | Missing or unclear evidence; never imputed as zero |
| `NOT_APPLICABLE_IN_MVP` | Blank / null | Fixed pack exclusion, currently one PC; never scored |
| `DECLARATION_OR_ASSESSOR_NOTE` | Blank / null | All 48 non-rubric PCs; blank task/marks and empty anchors |

`reference_kind=synthetic_reference` explicitly means scenario expectations,
never expert labels. PC anchors are copied into CSV JSON cells verbatim. The
`ambiguity` field is a hypothetical simulation input in [0,1], not a measured
quality/confidence estimate. Package PC entries reference the same IDs and values.

Every evidence row says `media_available=false`, `METADATA_ONLY` and
`NO_MEDIA_TO_REVIEW`. The convention
`synthetic-fixture://d3-synthetic-v1/SIM-001/T1` identifies a metadata fixture;
it is **not a file path or playback URL**. `scenario_availability` and
`scenario_reviewability` describe fiction only. No media hash, signature,
capture/upload success, biometric, private recording or photograph is fabricated.

## Scenario and simulation policy

Five packages each model strong performance, minor faults, major faults and
incomplete evidence. Strong/incomplete observable levels are predominantly 3 with
individual PC variation. Minor faults predominantly receive 2, with occasional
noncritical level 1. Major faults receive 0/1/2 and include explicit critical-PC
failures. Incomplete packages omit a rotating task (including T1 safety) and
some additional PC observations. All fictional omissions remain unscored.

The three stable rater IDs are `SIM_RATER_01`, `SIM_RATER_02`, `SIM_RATER_03`.
Baseline severity parameters are −0.18, 0, +0.18, shifting the direction of an
occasional rating perturbation. Perturbation probability is
`(0.10 + 0.38 * ambiguity)`, multiplied by 0.55 on critical PCs. Perturbations
are normally one level; 4% of perturbations are two levels, clipped to 0–3.
A demonstrated PC additionally has probability `0.035 * ambiguity` of being
judged not observable. Reference unobservable/fixed unscored statuses always stay
unscored. These parameters are hypothetical engineering choices, uncalibrated
against assessors. The simulator intentionally consumes the scenario reference
to generate errors; analysis never uses references to repair scores or select
an assumed assistance benefit.

**Baseline uses identical parameters in both conditions**, with independent,
identity-keyed SHA-256-seeded random streams. There is no programmed assistance
improvement, no selected best seed and no positive-improvement acceptance gate.
The canonical baseline actually has lower assisted QWK/exact agreement.

An additional control uses the same draws as well as the same parameters:

```sh
python ml/study/simulate_ratings.py --policy identical --seed 42 \
  --out /tmp/d3-identical.csv
python ml/study/agreement.py /tmp/d3-identical.csv \
  --reference ml/study/data/expected_pc_levels.csv \
  --bootstrap 2000 --seed 42 --out /tmp/d3-identical-report.md
```

Defined differences and their intervals must be zero. This control is tested.
No hypothetical assistance-effect scenario is needed or included.

## Statistical contract

PC items are `(package,pc)` identities. The expected rater roster defaults to the
union of observed raters; pass `--raters SIM_RATER_01 SIM_RATER_02 SIM_RATER_03`
when assessing an externally supplied subset so an entirely absent rater is
detectable. Strict dataset validation always knows all three expected raters.
All PC agreement metrics use the shared set where every expected rater scored
the item in both conditions, within common packages. The exclusion ledger is
exhaustive: noncommon package, incomplete roster, fixed unscored status, then
not observable. MAE additionally requires a demonstrated reference. Complete-case
selection can favor easier evidence, so the report includes raw status counts,
missing rater slots, excluded item/record counts and absent reference counts.

QWK uses quadratic disagreement weights `(i-j)^2` on fixed levels 0–3. All
rater-pair statistics are reported; the mean is unavailable if any pair is
undefined. Fleiss kappa uses pooled category marginals and the constant full
roster. Exact agreement is the percentage of full-roster groups with one shared
level. SD is population SD (`ddof=0`) averaged equally over items. MAE weights
each retained rater/item observation equally. None is weighted by PC marks.
Absent categories remain zero-count columns, never missing ordinal levels.

For outcome-category Fleiss/exact agreement, each included package must contain
all 71 pinned task-linked PC records for every rater in both conditions, including
explicit unobservable/not-applicable statuses. `outcome_adapter.py` builds
read-only inputs for the existing `server/app/outcome.py`, applying exactly the
per-PC Decimal rounding from `routers/scoring.py`. It preserves the engine's
not-applicable denominator behavior without granting a score to that PC. Outcome
categories are nominal; no ordinal outcome kappa or replacement threshold rule
is invented. Incomplete packages are excluded jointly and counted.

The paired bootstrap samples entire common packages with replacement, preserving
every retained PC, rater and both conditions. Distinct internal draw identities
represent repeated draws; additive package sufficient statistics preserve their
full multiplicity. A repeated package is never deduplicated. By default 2000
draws with seed 42 produce 2.5/97.5 percentile intervals for
`rubric_assisted - manual`, using linear interpolation. Higher QWK/Fleiss/exact
and lower SD/MAE indicate improvement. Intervals need ≥2 common packages, defined
point statistics and ≥95% defined draws (at least two); undefined draws and
unavailable reasons are reported. CIs describe synthetic package variability,
not real-assessor uncertainty or causal effects. With one rater, only MAE is
available. Degenerate kappa remains unavailable even for exact agreement of 100%.

`--gold` is a compatibility alias for `--reference`; output always calls these
synthetic references. Corrupt CSV, invalid levels and duplicate identities fail
with nonzero exit status. Missing records produce explicit exclusions, not a
silently reduced rater roster or imputed scores.

Independent numerical checks use
[scikit-learn quadratic Cohen kappa](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.cohen_kappa_score.html)
and [statsmodels Fleiss kappa](https://www.statsmodels.org/stable/generated/statsmodels.stats.inter_rater.fleiss_kappa.html),
plus hand calculations for every metric and literal expansion of repeated
bootstrap clusters. NumPy independently checks SD, MAE, exact agreement and
percentile interpolation. [SciPy's bootstrap documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html)
describes paired resampling and percentile intervals; here the resampling unit
is explicitly the assessment package rather than the PC row.

## P10 handoff

P10 can immediately run `reproduce.py --check`, choose a `SIM-*` scenario, inspect
the manifest/reference/rating CSVs and display the generated report with its
synthetic limitation visible. Filter the single rating CSV by `condition` to
obtain the paired manual/assisted inputs. Use the JSON report for metric values,
CIs and exclusions; use the Markdown report for review. Keep the fixture URI
convention separate from production media URLs and real assessment identifiers.

P10 still needs its own offline end-to-end application demonstration, real device
performance/runtime/memory measurements, real registration/capture/review/seal/
sync/report workflows, and any planned study-mode dashboard integration. No new
UI or backend endpoint was built here. If P10 needs a study API, it must explicitly
define an isolated read-only synthetic-data interface and authorization; this is
a P10 dependency, not a production DB import. Existing Q4/P8 field/device gaps
remain as documented in their gates; D3 does not close them. A future human study
needs independent assessors, participants, consent, real evidence and separately
identified reference collection. This synthetic dataset cannot satisfy it.
