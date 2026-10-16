# D3 synthetic dataset validation

**This report uses synthetic packages, synthetic reference scores and simulated raters. It validates the software and statistics only. It is not evidence of agreement improvement among real assessors.**

MVP assessor-support rubric; not an official SSC scoring replacement.
Rubric status: draft — pending trade-expert sign-off (P1 exit test).

Validation: **PASS** (strict schemas, complete identities, source/artifact hashes, pinned anchors/marks, evidence semantics and production outcomes).

Reproducibility: **PASS — byte-identical regeneration of every dataset artifact**.

Generator `d3-synthetic-v1`, seed 42; simulation `baseline`, seed 42.
QP CON/Q0602 v4.0; rubric `ae-con-q0602@v4.0-r1`.

## Counts and missing data

```json
{
  "conditions": 2,
  "critical_pcs": 26,
  "critical_violation_packages": [
    "SIM-011",
    "SIM-012",
    "SIM-013",
    "SIM-014",
    "SIM-015"
  ],
  "distinct_pcs": 119,
  "distinct_tasks": 5,
  "expected_outcome_distribution": {
    "INSUFFICIENT_EVIDENCE": 5,
    "NOT_YET_COMPETENT": 5,
    "RECOMMEND_CERTIFICATION": 10
  },
  "packages": 20,
  "raters": 3,
  "rating_level_distribution": {
    "manual": {
      "0": 468,
      "1": 524,
      "2": 1201,
      "3": 1632
    },
    "rubric_assisted": {
      "0": 443,
      "1": 513,
      "2": 1243,
      "3": 1619
    }
  },
  "rating_records": 14280,
  "rating_status_counts": {
    "DECLARATION_OR_ASSESSOR_NOTE": 5760,
    "DEMONSTRATED": 7643,
    "NOT_APPLICABLE_IN_MVP": 120,
    "NOT_OBSERVABLE": 757
  },
  "reference_level_distribution": {
    "0": 155,
    "1": 147,
    "2": 423,
    "3": 569
  },
  "reference_rows": 2380,
  "reference_status_counts": {
    "DECLARATION_OR_ASSESSOR_NOTE": 960,
    "DEMONSTRATED": 1294,
    "NOT_APPLICABLE_IN_MVP": 20,
    "NOT_OBSERVABLE": 106
  },
  "safety_evidence_omitted_packages": [
    "SIM-016"
  ],
  "scenarios": {
    "incomplete_evidence": 5,
    "major_faults": 5,
    "minor_faults": 5,
    "strong": 5
  },
  "task_linked_pcs": 71,
  "task_references": 100,
  "unobservable_critical_reference_rows": 37
}
```

All 119 QP PCs are represented per package: 71 task-linked (one fixed not-applicable), plus 48 declaration/notes only. Each declaration-only row has blank task, marks and level, and empty anchors. The 70 assessable PCs can be demonstrated or not observable. Blank CSV levels and JSON null values are never level 0. A demonstrated zero represents an observed deficient scenario outcome.

There is exactly one metadata-only fixture reference per package/task; no media file exists. `media_available=false` and `NO_MEDIA_TO_REVIEW` apply throughout. Fictional availability/reviewability fields are scenario inputs, never capture/upload/signature verification results. No private Q2/Q3 media is accessed.

## Source and artifact SHA-256

```json
{
  "artifact_sha256": {
    "evidence_manifest.jsonl": "bc8318020c5f6370aa07db36597c0bf88ccc3afaeabdafb39a76a4a7f8b3a92b",
    "expected_pc_levels.csv": "2a5ec93b8562d8618162f912bddbece098c63ab2581f4ecee62330ad94e40c1c",
    "packages.jsonl": "ecbd214b44a0580104fde3df05eb607cc0213a14b73826c23d2ac739876b0061",
    "simulated_ratings.csv": "5423f28674f354335d6f7b781588566789fcbc18dcc47616f576cf1258486c68"
  },
  "source_sha256": {
    "ml/study/agreement.py": "12cd44625ab5036159db036465ed056375cf9c6432582f71902b48744cf32494",
    "ml/study/common.py": "56753eb9172a806dcd275a51104f084cbe0feaed76ed313df0f55beff261ca55",
    "ml/study/generate_demo_data.py": "18319cc18f1d4ecf2179f9bcc4ce82287a9ab7912d7b09f0fd08cdd2d195538d",
    "ml/study/outcome_adapter.py": "fa0cb3fb92e340529a6c0140f5732024196dd6055b19509d57cdbbe3a66556d2",
    "ml/study/reproduce.py": "5129da2ae19a7fa8d2cba33c2a7b0a19809e67b6488b0079865a94fae9d3ac95",
    "ml/study/requirements-test.txt": "af2a8130cb8f7e9bacc51b2c1b47b4db01598e387276a8cef7d84aabc27baacb",
    "ml/study/simulate_ratings.py": "501315d6f40cafb372c9e771d6d735417231e2ad61d271fbef9a3422a37e5168",
    "ml/study/validate_dataset.py": "9c5ca899b2e4d34877153e868d300e8e2ad0d03b388be907cf7347688cbed713",
    "packs/ae-con-q0602/coverage_matrix.json": "ab4c3be900875b10998a00a27b3823878adf5c69a5ce6dc611aadba6a48de28e",
    "packs/ae-con-q0602/qp.json": "d7a99a144dc94047a476633af229dded0056830b41ef49fc91229a20a7a0ed8f",
    "packs/ae-con-q0602/rubric.json": "1acb1b06ec3fa99762a5da6a2b31c3cd23434015af8d552e656fb8998f0bce46",
    "packs/ae-con-q0602/tasks.json": "e07a1946792240063cd068348378b1453050a174d49bcf2fd9f0c903bae19138",
    "server/app/outcome.py": "0e547bb571d9a9e243022be4b084e631d15f5df80e23173af224de6e50e68c1b",
    "server/app/routers/scoring.py": "f613d1a181afac583995feb59b13b4b201b9304293dc2d2bee159d21a60c4a15"
  }
}
```

Source version is the explicit generator version plus the recorded content hashes, independent of checkout directory, clock and Git commit. Hashes refer to actual committed-pack and generated text files, never nonexistent media.

## Boundaries

Synthetic reference values are controlled scenario expectations, not expert gold. No real assessor study, physical assessment collection, P10 device benchmark or offline product demonstration was performed by this pipeline. Original physical D3/D5 requirements remain unfulfilled. The draft rubric still requires trade-expert sign-off. P10 may reuse these fixtures only with the synthetic provenance visible.
