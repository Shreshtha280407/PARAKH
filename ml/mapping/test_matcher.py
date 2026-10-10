#!/usr/bin/env python3
"""Minimal self-check for matcher.py. Run: python3 ml/mapping/test_matcher.py"""
from pathlib import Path

from matcher import load_rules, match, normalize_declaration, validate_declaration

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
    """C12 = 'Connected an earth wire'; keywords.json maps earthing terms to it."""
    without = match({"answers": {"C12": "never"}, "free_text": ""}, RULES)
    with_kw = match({"answers": {"C12": "never"}, "free_text": "did earthing at a site"}, RULES)
    assert with_kw["overall_coverage"] > without["overall_coverage"]


def test_hindi_keyword_boosts_coverage():
    """Devanagari free text must hit keywords.json's "hi" lists (not just transliterated)."""
    without = match({"answers": {"C12": "never"}, "free_text": ""}, RULES)
    with_hi = match({"answers": {"C12": "never"}, "free_text": "मैंने अर्थिंग का काम किया"}, RULES)
    assert with_hi["overall_coverage"] > without["overall_coverage"], with_hi
    without_c17 = match({"answers": {"C17": "never"}, "free_text": ""}, RULES)
    with_hi_c17 = match({"answers": {"C17": "never"}, "free_text": "मैंने हेलमेट पहना"}, RULES)
    assert with_hi_c17["overall_coverage"] > without_c17["overall_coverage"], with_hi_c17


def test_hinglish_keyword_boosts_coverage():
    without = match({"answers": {"C12": "never"}, "free_text": ""}, RULES)
    with_hinglish = match({"answers": {"C12": "never"}, "free_text": "maine earthing kiya tha"}, RULES)
    assert with_hinglish["overall_coverage"] > without["overall_coverage"], with_hinglish
    without_c18 = match({"answers": {"C18": "never"}, "free_text": ""}, RULES)
    with_hinglish_c18 = match({"answers": {"C18": "never"}, "free_text": "tool box talk attend kiya"}, RULES)
    assert with_hinglish_c18["overall_coverage"] > without_c18["overall_coverage"], with_hinglish_c18


def test_free_text_never_overrides_structured_often():
    """An explicit structured 'often' must not be lowered by unrelated free text --
    the keyword boost is additive (raises below-sometimes answers), never a downgrade.
    C08 = 'Shifted or moved a temporary light/board to another spot', linked to CON/N0605.PC16."""
    r = match({"answers": {"C08": "often"}, "free_text": "no electrical work at all"}, RULES)
    assert r["nos_coverage"]["CON/N0605"] > 0


def test_t1_safety_appears_in_applicable_tasks():
    """Regression test for the r1 gap: CON/N9001 (Safety & PPE, task T1) must be
    scored and must appear in applicable_tasks -- it never did under r1."""
    r = match({"answers": {}}, RULES)
    task_ids = {t["task"] for t in r["applicable_tasks"]}
    assert task_ids == {"T1", "T2", "T3", "T4", "T5"}, task_ids
    assert "CON/N9001" in r["nos_coverage"]
    t1 = next(t for t in r["applicable_tasks"] if t["task"] == "T1")
    assert t1["nos"] == "CON/N9001"
    assert t1["extra_evidence_needed"] is True


def test_declaration_contract_is_20_cards_6_tools():
    """Q-1/P-3 worker-flow contract: exactly 20 declaration cards + 6 tools --
    CON/N8001 (teamwork) and CON/N8002 (plan & organise) have no cards at all
    any more (no declaration_only_signals side-channel either, see matcher.py)."""
    assert len(RULES["links"]["cards"]) == 20
    assert len(RULES["links"]["tools"]) == 6
    all_nos = {link["nos"] for item_links in
               [c["links"] for c in RULES["links"]["cards"]] + [t["links"] for t in RULES["links"]["tools"]]
               for link in item_links}
    assert "CON/N8001" not in all_nos
    assert "CON/N8002" not in all_nos


def test_rules_version_is_r3():
    r = match({"answers": {}}, RULES)
    assert r["rules_version"] == "match-rules@r3", r["rules_version"]


# --- validation: malformed declaration inputs must raise a clear ValueError ---

def test_rejects_unknown_item_id():
    try:
        match({"answers": {"NOT_A_REAL_CARD": "often"}}, RULES)
        raise AssertionError("expected ValueError for unknown item id")
    except ValueError as e:
        assert "NOT_A_REAL_CARD" in str(e)


def test_rejects_unsupported_claim_strength():
    try:
        match({"answers": {"C01": "always"}}, RULES)
        raise AssertionError("expected ValueError for unsupported claim strength")
    except ValueError as e:
        assert "C01" in str(e)


def test_rejects_duplicate_id_in_list_form():
    try:
        match({"answers": [{"item_id": "C01", "answer": "often"},
                            {"item_id": "C01", "answer": "never"}]}, RULES)
        raise AssertionError("expected ValueError for duplicate item_id")
    except ValueError as e:
        assert "C01" in str(e)


def test_rejects_non_object_declaration():
    try:
        match("not a declaration", RULES)
        raise AssertionError("expected ValueError for non-object declaration")
    except ValueError:
        pass


def test_rejects_non_string_free_text():
    try:
        match({"answers": {}, "free_text": 12345}, RULES)
        raise AssertionError("expected ValueError for non-string free_text")
    except ValueError:
        pass


def test_list_form_normalizes_to_same_result_as_dict_form():
    dict_form = match({"answers": {"C01": "often", "TL01": "sometimes"}}, RULES)
    list_form = match({"answers": [{"item_id": "C01", "answer": "often"},
                                    {"item_id": "TL01", "answer": "sometimes"}]}, RULES)
    assert dict_form == list_form


def test_normalize_declaration_defaults_missing_keys():
    normalized = normalize_declaration({})
    assert normalized == {"answers": {}, "free_text": ""}
    validate_declaration(normalized, RULES)  # must not raise


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"ml/mapping/test_matcher.py: all {len(tests)} checks passed")
