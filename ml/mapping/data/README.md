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
**not** real worker data and must not be used for the IC-1 ≥90% agreement
go/no-go gate (master plan §7, §8). That gate needs field-collected
declarations from real candidates, labelled by the trade expert against
their actual interview/experience, saved **without** a `harness_marker`
field — collecting and labelling that set is a P1/IC-1 task for AI-1 + the
trade expert, not something this script can produce.

Regenerate this fixture (if `packs/ae-con-q0602/mapping/` cards change)
with the generator kept in this repo's history / scratch tooling — it is a
thin wrapper around `ml/mapping/matcher.py`'s own card list, not checked in
as a permanent tool since it has no further purpose once real data lands.
