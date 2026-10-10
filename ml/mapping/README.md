# ml/mapping/

The deterministic CON/Q0602 declaration matcher (match-rules@r2) and its
test harness. Kotlin port lives at `apps/android/core/mapping` and must
agree with this matcher on every vector in `golden_vectors.jsonl` — see
`docs/gates/Q1.md` and `docs/gates/P3.md`.

| File | Role |
|---|---|
| `matcher.py` | The matcher itself. Pure stdlib, no model weights. Reads `packs/ae-con-q0602/mapping/*.json`. Includes `normalize_declaration`/`validate_declaration` for malformed-input rejection. |
| `eval.py` | CLI: run the matcher against a labelled `.jsonl` set, report agreement. See its docstring for `--mode harness` vs `--mode field`. |
| `test_matcher.py` | Structural self-check, HI/Hinglish keyword tests, validation-rejection tests, declaration-only-signal invariant, T1/safety regression test. `python3 ml/mapping/test_matcher.py` |
| `golden_vectors.jsonl` | 100 `(declaration -> full matcher output)` pairs — the Python-side half of the "Python/Kotlin must agree on all 100 golden vectors" requirement. Generated, not hand-written — see `generate_golden_vectors.py`. |
| `generate_golden_vectors.py` | Regenerates `golden_vectors.jsonl` deterministically (seeded) from the current rules, covering every required scenario category (see its own assertions + `docs/gates/Q1.md`). Re-run after any `mapping/*.json` or `matcher.py` change. |
| `test_golden_vectors.py` | Checks all 100 golden vectors reproduce exactly and the matcher is deterministic. `python3 ml/mapping/test_golden_vectors.py` |
| `data/labelled_60.jsonl` | Synthetic, `HARNESS_ONLY_NOT_FIELD_VALIDATION`-marked fixture for `eval.py`'s harness mode. See `data/README.md`. |
| `generate_labelled_60.py` | Regenerates `data/labelled_60.jsonl` (seeded, three archetypes, labels assigned independently of the matcher formula). |

Run everything:
```
python3 ml/mapping/test_matcher.py && \
python3 ml/mapping/test_golden_vectors.py && \
python3 ml/mapping/eval.py --rules packs/ae-con-q0602/mapping --set ml/mapping/data/labelled_60.jsonl
```

Regenerate the contract/fixture after a rules change:
```
python3 ml/mapping/generate_golden_vectors.py
python3 ml/mapping/generate_labelled_60.py
python3 ml/mapping/test_golden_vectors.py   # confirm it still passes
```

No independent assessor-agreement study is in scope here — see
`docs/gates/IC1A.md`.
