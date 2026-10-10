# ml/mapping/data/

`labelled_60.jsonl` is a **synthetic**, `HARNESS_ONLY_NOT_FIELD_VALIDATION`-marked
fixture generated from three worker archetypes (experienced / partial /
unrelated), with each record's `expected_match` label assigned by archetype
— independently of the matcher's own coverage formula — so that `eval.py`'s
agreement number is a real check rather than a circular one.

Every record carries `"harness_marker": "HARNESS_ONLY_NOT_FIELD_VALIDATION"`.
`ml/mapping/eval.py` enforces this mechanically: its default `--mode harness`
requires every record to carry that marker and always prints a synthetic-data
banner, and it never reports an IC-1 PASS/FAIL verdict in that mode — only
"informational" numbers. The complementary `--mode field` requires the
*opposite* (zero records may carry the marker) and refuses to run against
this file for exactly that reason. This makes "quote `labelled_60.jsonl`'s
agreement number as if it were IC-1 field validation" a hard error, not a
documentation request someone can skip.

It exists so `ml/mapping/eval.py` has something to run against for the P1
exit test ("first 20 labelled declarations run without errors"). It is
**not** real worker data and must not be used for an IC-1-style expert
agreement go/no-go claim. Independent assessor-agreement validation is
**out of scope for Q-1/P-3 entirely** — see `docs/gates/IC1A.md`, which
replaces the earlier expert-agreement IC-1 wording with a truthful
technical-only gate. A real agreement study (field-collected declarations
from real candidates, labelled by a trade expert against their actual
interview/experience, saved **without** a `harness_marker` field) belongs
to a later pilot/study phase, not Q-1/P-3.

Regenerate this fixture (if `packs/ae-con-q0602/mapping/` cards change) with
`python3 ml/mapping/generate_labelled_60.py` — a seeded, reproducible,
three-archetype (experienced / partial / unrelated) generator kept in this
repo. Each record's `expected_match` is assigned by archetype design, not
computed from `matcher.match()`, so `eval.py`'s agreement number stays a
real check rather than a circular one.
