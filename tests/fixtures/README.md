# Negative fixtures

Each fixture is a copy of `packs/ae-con-q0602/` with exactly one deliberate
defect, used by `tools/pack_validate.py` and/or `tools/audit_qp_traceability.py`
in the P1 technical audit. None include the QP PDF — the `[qp]` check in
`pack_validate.py` skips the hash comparison when the PDF file is absent,
which is expected here. Each fixture is verified to fail **only** its
targeted check and pass everything else, so a failure here always points at
one specific defect, not a cascade.

| Fixture | Defect | Caught by | Check that fails |
|---|---|---|---|
| `pack_121mb/` | `tasks.json` T5 budget bumped to 31 MB (121 MB total) | `pack_validate.py` | `[tasks]` |
| `pack_missing_pc_task/` | `tasks.json` T2 has `CON/N0602.PC9` removed from `linked_pcs` — a practical PC with no task coverage | `pack_validate.py` and `audit_qp_traceability.py` | `[links]` and `[coverage]` |
| `pack_wrong_qp_version/` | `qp.json.version` set to `"3.0"` while `source.json.qp_version` stays `"4.0"` — simulates an un-synced version bump | `audit_qp_traceability.py` | `[source]` |
| `pack_unknown_pc_ref/` | `tasks.json` T2 has a typo'd/nonexistent PC id (`CON/N0602.PC99`, which doesn't exist — N0602 only has 11 PCs) appended to `linked_pcs` | `audit_qp_traceability.py` | `[refs]` |

A fifth case has no fixture directory because the defect is a command flag,
not a file:

- **Attempt to label synthetic data as field validation**: run
  `python ml/mapping/eval.py --rules packs/ae-con-q0602/mapping --set ml/mapping/data/labelled_60.jsonl --mode field`.
  `labelled_60.jsonl` carries `"harness_marker": "HARNESS_ONLY_NOT_FIELD_VALIDATION"`
  on every record; `--mode field` refuses to run against any dataset where a
  record carries that marker. Exit 1, no agreement number printed.

Run all of them:

```
python tools/pack_validate.py tests/fixtures/pack_121mb                  # -> exit 1, [tasks]
python tools/pack_validate.py tests/fixtures/pack_missing_pc_task        # -> exit 1, [links]
python tools/audit_qp_traceability.py tests/fixtures/pack_missing_pc_task # -> exit 1, [coverage]
python tools/audit_qp_traceability.py tests/fixtures/pack_wrong_qp_version # -> exit 1, [source]
python tools/audit_qp_traceability.py tests/fixtures/pack_unknown_pc_ref  # -> exit 1, [refs]
python ml/mapping/eval.py --rules packs/ae-con-q0602/mapping --set ml/mapping/data/labelled_60.jsonl --mode field  # -> exit 1, refuses
```
