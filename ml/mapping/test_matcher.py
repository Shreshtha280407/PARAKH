#!/usr/bin/env python3
"""Minimal self-check for matcher.py. Run: python3 ml/mapping/test_matcher.py"""
from pathlib import Path

from matcher import load_rules, match

RULES = load_rules(Path(__file__).parent.parent.parent / "packs/ae-con-q0602/mapping")


def test_all_often_is_appropriate():
    answers = {c["id"]: "often" for c in RULES["links"]["cards"]}
    answers.update({t["id"]: "often" for t in RULES["links"]["tools"]})
    r = match({"answers": answers}, RULES)
    assert r["match_result"] == "appropriate_match", r
    assert r["overall_coverage"] >= 0.60


def test_all_never_is_not_appropriate():
    r = match({"answers": {}}, RULES)
    assert r["match_result"] == "not_appropriate_match", r
    assert r["overall_coverage"] == 0.0
    assert all(not v for v in r["nos_has_experience"].values())


def test_never_decides_competence_contract():
    r = match({"answers": {}}, RULES)
    assert set(r.keys()) >= {"match_result", "overall_coverage", "nos_coverage", "because", "gap_nos"}
    assert r["match_result"] in {"appropriate_match", "partial_match", "not_appropriate_match"}


def test_keyword_boosts_never_to_sometimes():
    without = match({"answers": {"C08": "never"}, "free_text": ""}, RULES)
    with_kw = match({"answers": {"C08": "never"}, "free_text": "did earthing at a site"}, RULES)
    assert with_kw["overall_coverage"] > without["overall_coverage"]


if __name__ == "__main__":
    test_all_often_is_appropriate()
    test_all_never_is_not_appropriate()
    test_never_decides_competence_contract()
    test_keyword_boosts_never_to_sometimes()
    print("ml/mapping/test_matcher.py: all checks passed")
