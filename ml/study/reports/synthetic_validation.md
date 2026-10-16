# D3 synthetic engineering validation

**This report uses synthetic packages, synthetic reference scores and simulated raters. It validates the software and statistics only. It is not evidence of agreement improvement among real assessors.**

MVP assessor-support rubric; not an official SSC scoring replacement.
Rubric status: draft — pending trade-expert sign-off (P1 exit test).

QP CON/Q0602 v4.0; rubric `ae-con-q0602@v4.0-r1`.

No real assessors participated; no expert labels were collected. Original physical D3/D5 requirements remain unfulfilled.

| Metric | Manual | Rubric assisted | Difference (assisted − manual) | 95% package bootstrap CI | Improvement direction |
|---|---:|---:|---:|---|---|
| Mean pairwise QWK | 0.852201 | 0.849026 | -0.003175 | [-0.026922, 0.017650] | higher |
| Fleiss' kappa | 0.622386 | 0.610862 | -0.011524 | [-0.055643, 0.025082] | higher |
| Exact agreement (%) | 62.680237 | 61.323155 | -1.357082 | [-5.850631, 2.267827] | higher |
| Mean rating SD | 0.191442 | 0.194547 | 0.003105 | [-0.015929, 0.027263] | lower |
| MAE vs synthetic reference | 0.159457 | 0.156347 | -0.003110 | [-0.020954, 0.017218] | lower |
| Outcome Fleiss' kappa | 0.249218 | 0.350766 | 0.101549 | [-0.153225, 0.380498] | higher |
| Outcome exact agreement (%) | 40.000000 | 40.000000 | 0.000000 | [-20.000000, 20.000000] | higher |

## Interpretation and method

Baseline simulation assigns the same parameters to both conditions and draws independent errors. Differences reflect controlled simulation noise; they are not a measured product effect. Labels are not inferred or corrected by the analysis.
Simulation metadata: policies ['baseline']; seeds ['42'].

Quadratic-weighted Cohen kappa uses fixed ordered categories 0–3 and weights (i−j)². The mean requires every rater pair to be defined. Fleiss kappa uses pooled category marginals and a constant full roster. Exact agreement is the percentage of item groups where every rater gives the same level. Mean SD averages population SD (ddof=0) per item. MAE is an unweighted mean over rater/item observations with a demonstrated reference; PC marks do not weight these statistics.

All PC statistics use the joint complete, demonstrated item set across both conditions. MAE additionally excludes missing/unscored reference labels. This complete-case comparison can select easier evidence; status counts and excluded items below expose that limitation. Unobservable, not-applicable and declaration-only values never become scored zeroes. With one rater only MAE is meaningful.

Outcome agreement is nominal Fleiss kappa and exact agreement over complete 71-PC packages, including explicit unobservable/not-applicable statuses. It calls `server/app/outcome.py` with the existing scoring Decimal rounding. The existing engine keeps not-applicable marks in the denominator; this adapter preserves that behavior. These are computed recommendations, not official certification decisions.

Bootstrap: 2000 draws, seed 42. Resample entire common packages with replacement, using the same draw in both conditions and a distinct internal identity for every repeated draw. Additive per-package sufficient statistics preserve all PCs and raters without collapsing repeated packages. Percentile endpoints use linear interpolation. No row bootstrap or normal approximation is used.

CIs require at least two clusters, a defined point difference and ≥95% defined replicates (at least two). Undefined replicates are counted below; intervals then describe the defined replicates. These intervals describe the synthetic package population, not people, independent field evidence or causal effects.

## Pairwise quadratic-weighted Cohen kappa

| Rater pair | Manual | Rubric assisted |
|---|---:|---:|
| SIM_RATER_01 / SIM_RATER_02 | 0.842734 | 0.847178 |
| SIM_RATER_01 / SIM_RATER_03 | 0.855031 | 0.846329 |
| SIM_RATER_02 / SIM_RATER_03 | 0.858839 | 0.853570 |

## Cohort and exclusions

Input: 14280 rating records; 2380 reference records; 3 raters; 20 common packages.
Candidate package/PC identities: 2380; retained complete scored items: 1179.

Item exclusions are mutually exclusive, in priority order: noncommon package, incomplete roster, fixed unscored status, not observable. MAE exclusions are additional and apply only to retained items.

```json
{
  "candidate_package_pc_items": 2380,
  "common_packages": [
    "SIM-001",
    "SIM-002",
    "SIM-003",
    "SIM-004",
    "SIM-005",
    "SIM-006",
    "SIM-007",
    "SIM-008",
    "SIM-009",
    "SIM-010",
    "SIM-011",
    "SIM-012",
    "SIM-013",
    "SIM-014",
    "SIM-015",
    "SIM-016",
    "SIM-017",
    "SIM-018",
    "SIM-019",
    "SIM-020"
  ],
  "excluded_existing_rating_records_by_reason": {
    "fixed_unscored_status_in_either_condition": 5880,
    "not_observable_in_either_condition": 1326
  },
  "excluded_items_by_reason": {
    "fixed_unscored_status_in_either_condition": 980,
    "not_observable_in_either_condition": 221
  },
  "input_rating_records": 14280,
  "input_status_counts": {
    "manual": {
      "DECLARATION_OR_ASSESSOR_NOTE": 2880,
      "DEMONSTRATED": 3825,
      "NOT_APPLICABLE_IN_MVP": 60,
      "NOT_OBSERVABLE": 375
    },
    "rubric_assisted": {
      "DECLARATION_OR_ASSESSOR_NOTE": 2880,
      "DEMONSTRATED": 3818,
      "NOT_APPLICABLE_IN_MVP": 60,
      "NOT_OBSERVABLE": 382
    }
  },
  "mae_excluded_items_missing_reference": 0,
  "mae_excluded_items_unscored_reference": 0,
  "missing_rater_slots_by_condition": {
    "manual": 0,
    "rubric_assisted": 0
  },
  "outcome_distributions": {
    "manual": {
      "INSUFFICIENT_EVIDENCE": 21,
      "NOT_YET_COMPETENT": 35,
      "RECOMMEND_CERTIFICATION": 4
    },
    "rubric_assisted": {
      "INSUFFICIENT_EVIDENCE": 26,
      "NOT_YET_COMPETENT": 25,
      "RECOMMEND_CERTIFICATION": 9
    }
  },
  "outcome_excluded_common_packages_incomplete_pack": 0,
  "packages_by_condition": {
    "manual": [
      "SIM-001",
      "SIM-002",
      "SIM-003",
      "SIM-004",
      "SIM-005",
      "SIM-006",
      "SIM-007",
      "SIM-008",
      "SIM-009",
      "SIM-010",
      "SIM-011",
      "SIM-012",
      "SIM-013",
      "SIM-014",
      "SIM-015",
      "SIM-016",
      "SIM-017",
      "SIM-018",
      "SIM-019",
      "SIM-020"
    ],
    "rubric_assisted": [
      "SIM-001",
      "SIM-002",
      "SIM-003",
      "SIM-004",
      "SIM-005",
      "SIM-006",
      "SIM-007",
      "SIM-008",
      "SIM-009",
      "SIM-010",
      "SIM-011",
      "SIM-012",
      "SIM-013",
      "SIM-014",
      "SIM-015",
      "SIM-016",
      "SIM-017",
      "SIM-018",
      "SIM-019",
      "SIM-020"
    ]
  },
  "raters": [
    "SIM_RATER_01",
    "SIM_RATER_02",
    "SIM_RATER_03"
  ],
  "reference_records": 2380,
  "reference_rows_without_any_ratings": 0,
  "retained_complete_scored_items": 1179
}
```

## Undefined values and bootstrap availability

- Mean pairwise QWK: 2000 defined / 0 undefined bootstrap differences.
- Fleiss' kappa: 2000 defined / 0 undefined bootstrap differences.
- Exact agreement (%): 2000 defined / 0 undefined bootstrap differences.
- Mean rating SD: 2000 defined / 0 undefined bootstrap differences.
- MAE vs synthetic reference: 2000 defined / 0 undefined bootstrap differences.
- Outcome Fleiss' kappa: 2000 defined / 0 undefined bootstrap differences.
- Outcome exact agreement (%): 2000 defined / 0 undefined bootstrap differences.

## Provenance

```json
{
  "analysis_source": "12cd44625ab5036159db036465ed056375cf9c6432582f71902b48744cf32494",
  "outcome_engine": "0e547bb571d9a9e243022be4b084e631d15f5df80e23173af224de6e50e68c1b",
  "ratings": "5423f28674f354335d6f7b781588566789fcbc18dcc47616f576cf1258486c68",
  "reference": "2a5ec93b8562d8618162f912bddbece098c63ab2581f4ecee62330ad94e40c1c"
}
```

Statistical cross-check sources: [scikit-learn QWK](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.cohen_kappa_score.html), [statsmodels Fleiss kappa](https://www.statsmodels.org/stable/generated/statsmodels.stats.inter_rater.fleiss_kappa.html). Unit tests compare these independent implementations and hand-calculated fixtures.
