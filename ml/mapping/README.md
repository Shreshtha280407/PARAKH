# ml/mapping/

The deterministic CON/Q0602 declaration matcher (match-rules@r1) and its
test harness.

| File | Role |
|---|---|
| `matcher.py` | The matcher itself. Pure stdlib, no model weights. Reads `packs/ae-con-q0602/mapping/*.json`. |
| `eval.py` | CLI: run the matcher against a labelled `.jsonl` set, report agreement. See its docstring for `--mode harness` vs `--mode field`. |
| `test_matcher.py` | Structural self-check (all-often → appropriate, all-never → not-appropriate, output contract, keyword boost). `python3 ml/mapping/test_matcher.py` |
| `golden_vectors.jsonl` | 100 `(declaration -> full matcher output)` pairs — the Python-side half of the master plan's "Python/Kotlin must agree on all 100 golden vectors" requirement. The Kotlin port doesn't exist yet (P3); until it does, this just pins Python's own determinism. |
| `test_golden_vectors.py` | Checks all 100 golden vectors reproduce exactly and the matcher is deterministic. `python3 ml/mapping/test_golden_vectors.py` |
| `data/labelled_60.jsonl` | Synthetic, `HARNESS_ONLY_NOT_FIELD_VALIDATION`-marked declarations for `eval.py`'s harness mode. See `data/README.md`. |

Run everything: `python3 ml/mapping/test_matcher.py && python3 ml/mapping/test_golden_vectors.py && python3 ml/mapping/eval.py --rules packs/ae-con-q0602/mapping --set ml/mapping/data/labelled_60.jsonl`
