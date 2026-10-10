#!/usr/bin/env python3
"""Generate ml/mapping/golden_vectors.jsonl — the 100-vector Python/Kotlin
match-rules@r3 parity contract (20 declaration cards + 6 tools).

This is the canonical, already-established location for the golden-vector
contract (see ml/mapping/README.md, matcher.py's module docstring, CI); it is
kept in preference to introducing a second contracts/mapping_vectors.json
location, per docs/gates/Q1.md's "preserve existing canonical location"
decision.

Every vector's expected_output is computed BY RUNNING matcher.py itself
(not hand-calculated), exactly like the r1 set this replaces — the value of
a golden vector is as a pinned, reproducible cross-language target for the
Kotlin port, not as an independently-derived ground truth (the matcher has
no ground truth beyond its own deterministic rules; see
docs/gates/IC1A.md for what these vectors do and do not prove).

Run: python3 ml/mapping/generate_golden_vectors.py
Then: python3 ml/mapping/test_golden_vectors.py
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from matcher import load_rules, match  # noqa: E402

ROOT = Path(__file__).parent.parent.parent
RULES = load_rules(ROOT / "packs/ae-con-q0602/mapping")
OUT_PATH = Path(__file__).parent / "golden_vectors.jsonl"

PRACTICAL_NOS = [e["nos"] for e in RULES["thresholds"]["practical_nos_for_matching"]]

ALL_CARD_IDS = [c["id"] for c in RULES["links"]["cards"]]
ALL_TOOL_IDS = [t["id"] for t in RULES["links"]["tools"]]
ALL_ITEM_IDS = ALL_CARD_IDS + ALL_TOOL_IDS

# Under r3 every card/tool touches at least one scored (practical) NOS -- unlike
# r2, teamwork/plan-and-organise (CON/N8001, CON/N8002) have no cards at all any
# more (see links.json r3 status / matcher.py), so this is just ALL_ITEM_IDS; kept
# as its own name since downstream code (single-item sweep, G011/G012) reads it.
PRACTICAL_ITEM_IDS = [
    item_id for item_id, links in
    [(c["id"], c["links"]) for c in RULES["links"]["cards"]] + [(t["id"], t["links"]) for t in RULES["links"]["tools"]]
    if any(l["nos"] in PRACTICAL_NOS for l in links)
]
assert set(PRACTICAL_ITEM_IDS) == set(ALL_ITEM_IDS), "r3 expects every card/tool to touch a scored NOS"

# Card IDs below are the r3 20-card scheme (packs/ae-con-q0602/mapping/links.json);
# see docs/qp_declaration_traceability.md for the full old-id -> new-id mapping.
SAFETY_ITEM_IDS = ["C17", "C18", "C19", "C20"]  # N9001-heavy
LIGHTING_RELATED = ["C02", "C04", "C06", "C07", "C08", "C09", "C10", "TL02"]  # N0603-heavy
WIRING_RELATED = ["C01", "C02", "C10", "C11", "C12", "C13", "TL05"]  # N0604-heavy
PANEL_RELATED = ["C04", "C05", "C07", "C08", "C09", "C12", "C13", "C14", "C15", "C16"]  # N0605-heavy
DOMESTIC_RELATED = ["C01", "C06", "C11", "TL03", "TL04"]
TOOLS_RELATED = ["C01", "C02", "C03", "C04", "C05", "TL01", "TL02", "TL03", "TL04", "TL06"]  # N0602-heavy

vectors = []
seen_ids = set()


def add(vec_id, category, declaration):
    if vec_id in seen_ids:
        raise RuntimeError(f"duplicate vector id {vec_id}")
    seen_ids.add(vec_id)
    output = match(declaration, RULES)
    vectors.append({"id": vec_id, "category": category, "input": declaration, "expected_output": output})


def answers_for(often=(), sometimes=(), never_rest_of=ALL_ITEM_IDS):
    a = {i: "never" for i in never_rest_of}
    for i in often:
        a[i] = "often"
    for i in sometimes:
        a[i] = "sometimes"
    return a


# ---------------------------------------------------------------------------
# 1. Named, spec-required scenario categories (32 vectors: G001-G032)
# ---------------------------------------------------------------------------

# strong Assistant Electrician profile (also serves as the all-often reference point)
add("G001", "strong_ae_profile", {
    "answers": {i: "often" for i in ALL_ITEM_IDS},
    "free_text": "many years doing house wiring, panel work and site safety",
})

# all-sometimes reference point
add("G002", "all_sometimes_reference", {"answers": {i: "sometimes" for i in ALL_ITEM_IDS}, "free_text": ""})

# no experience at all (explicit "never" on every item)
add("G003", "no_experience_explicit_never", {"answers": {i: "never" for i in ALL_ITEM_IDS}, "free_text": ""})

# blank/missing: empty answers dict, no free_text key
add("G004", "blank_missing_empty_answers", {"answers": {}})

# blank/missing: no "answers" key at all, no free_text key -- fully empty declaration
add("G005", "blank_missing_no_keys", {})

# temporary-lighting-heavy profile
add("G006", "temp_lighting_heavy", {
    "answers": answers_for(often=LIGHTING_RELATED, sometimes=["C02", "C19"]),
    "free_text": "mostly set up temporary lights and fixed lighting faults",
})

# LV-wiring-heavy profile
add("G007", "lv_wiring_heavy", {
    "answers": answers_for(often=WIRING_RELATED, sometimes=["C02", "C12"]),
    "free_text": "mostly did house wiring through conduit",
})

# DB/MCB/panel profile
add("G008", "db_mcb_panel_heavy", {
    "answers": answers_for(often=PANEL_RELATED, sometimes=["C02", "C19"]),
    "free_text": "mostly assembled distribution boards and MCBs",
})

# domestic-only electrical profile
add("G009", "domestic_only_electrical", {
    "answers": answers_for(often=DOMESTIC_RELATED, sometimes=["C12"]),
    "free_text": "only ever fixed switches and lights at home, never on a construction site",
})

# electrical helper with weak practical coverage
add("G010", "electrical_helper_weak_coverage", {
    "answers": answers_for(sometimes=["C01", "C12", "C18", "TL04"]),
    "free_text": "helped carry tools and materials for an electrician",
})

# strong safety, weak electrical practical profile
add("G011", "strong_safety_weak_electrical", {
    "answers": answers_for(often=SAFETY_ITEM_IDS, sometimes=["C01"]),
    "free_text": "",
})

# weak safety, strong electrical practical profile
add("G012", "weak_safety_strong_electrical", {
    "answers": answers_for(often=[i for i in PRACTICAL_ITEM_IDS if i not in SAFETY_ITEM_IDS]),
    "free_text": "",
})

# unrelated trade profiles -- plumber / mason / welder, English free text must NOT
# trigger any electrical keyword boost (keywords.json has no plumbing/masonry/welding terms)
add("G013", "unrelated_plumber", {
    "answers": answers_for(sometimes=["C12", "C15"]),
    "free_text": "I am a plumber, I fix pipes and taps, never done electrical work",
})
add("G014", "unrelated_mason", {
    "answers": answers_for(sometimes=["C12"]),
    "free_text": "I work as a mason laying bricks and plaster, no electrical experience",
})
add("G015", "unrelated_welder", {
    "answers": answers_for(sometimes=["C13", "TL06"]),
    "free_text": "I am a welder, I weld steel structures on site, not an electrician",
})

# contradictory declarations
add("G016", "contradictory_advanced_panel_no_basic_tools", {
    "answers": answers_for(often=["C05", "C07", "C14", "C16"] + SAFETY_ITEM_IDS, never_rest_of=ALL_ITEM_IDS),
    "free_text": "",
})
add("G017", "contradictory_safety_conscious_no_practical_skill", {
    "answers": answers_for(often=SAFETY_ITEM_IDS),
    "free_text": "",
})

# Hindi input (Devanagari free text), three different base profiles
add("G018", "hindi_input_strong", {
    "answers": answers_for(sometimes=PRACTICAL_ITEM_IDS),
    "free_text": "मैंने अर्थिंग का काम किया और मल्टीमीटर से टेस्टर चेक किया, डिस्ट्रीब्यूशन बोर्ड पर भी काम किया",
})
add("G019", "hindi_input_lighting", {
    "answers": {i: "never" for i in ALL_ITEM_IDS},
    "free_text": "लाइट पॉइंट लगाया और ट्यूबलाइट ठीक की, पैनल चेक किया",
})
add("G020", "hindi_input_safety", {
    "answers": {i: "never" for i in ALL_ITEM_IDS},
    "free_text": "हेलमेट पहना और सुरक्षा बैठक में गया, फर्स्ट एड बॉक्स चेक किया",
})

# Hinglish input, three different base profiles
add("G021", "hinglish_input_strong", {
    "answers": answers_for(sometimes=PRACTICAL_ITEM_IDS),
    "free_text": "maine earthing kiya aur tester se check kiya, db banaya aur panel wiring ki",
})
add("G022", "hinglish_input_wiring", {
    "answers": {i: "never" for i in ALL_ITEM_IDS},
    "free_text": "pipe me tar dala aur wall me wiring ki, switch board banaya",
})
add("G023", "hinglish_input_safety", {
    "answers": {i: "never" for i in ALL_ITEM_IDS},
    "free_text": "helmet pehna aur safety shoes pehne, tool box talk attend kiya",
})

# each individual practical NOS absent (also exercises every T1-T5 gap flag at least once)
NOS_TO_RELATED_ITEMS = {
    "CON/N0602": TOOLS_RELATED,
    "CON/N0603": LIGHTING_RELATED,
    "CON/N0604": WIRING_RELATED,
    "CON/N0605": PANEL_RELATED,
    "CON/N9001": SAFETY_ITEM_IDS,
}
nos_absent_idx = 24
for nos, related in NOS_TO_RELATED_ITEMS.items():
    others_often = [i for i in PRACTICAL_ITEM_IDS if i not in related]
    vec_id = f"G{nos_absent_idx:03d}"
    add(vec_id, f"nos_absent_{nos.replace('/', '_')}", {
        "answers": answers_for(often=others_often, never_rest_of=ALL_ITEM_IDS),
        "free_text": "",
    })
    nos_absent_idx += 1
# nos_absent_idx is now 29

# boundary cases around 0.35 and 0.60 -- fine-grained monotonic walk (never -> sometimes
# -> often, one step at a time, sorted item order) using the real matcher so the exact
# crossing point is whatever the rules actually produce, not a hand-picked float.
_walk_items = sorted(PRACTICAL_ITEM_IDS)
_state = {i: "never" for i in ALL_ITEM_IDS}
_sequence = [dict(_state)]
for item in _walk_items:
    _state[item] = "sometimes"
    _sequence.append(dict(_state))
    _state[item] = "often"
    _sequence.append(dict(_state))

_overalls = [match({"answers": s, "free_text": ""}, RULES)["overall_coverage"] for s in _sequence]


def _bracket(threshold):
    below = None
    above = None
    for s, o in zip(_sequence, _overalls):
        if o < threshold:
            below = s
        elif above is None:
            above = s
            break
    return below, above


_b35_below, _b35_above = _bracket(0.35)
_b60_below, _b60_above = _bracket(0.60)

add("G029", "boundary_below_0_35", {"answers": _b35_below, "free_text": ""})
add("G030", "boundary_at_or_above_0_35", {"answers": _b35_above, "free_text": ""})
add("G031", "boundary_below_0_60", {"answers": _b60_below, "free_text": ""})
add("G032", "boundary_at_or_above_0_60", {"answers": _b60_above, "free_text": ""})

# ---------------------------------------------------------------------------
# 2. Single-item sweeps -- isolate the effect of exactly one declaration item
#    answered "often", everything else "never". Covers all 20 r3 cards + 6 r3
#    tools (26 items total).
# ---------------------------------------------------------------------------
idx = 33
for item_id in sorted(ALL_ITEM_IDS):
    vec_id = f"G{idx:03d}"
    add(vec_id, f"single_item_often_{item_id}", {
        "answers": answers_for(often=[item_id]),
        "free_text": "",
    })
    idx += 1
# 26 single-item vectors -> idx now 33+26 = 59

# ---------------------------------------------------------------------------
# 3. Deterministic pseudo-random mixed declarations (seeded) to round out the
#    set to exactly 100 and add realistic, varied coverage/free-text mixes.
# ---------------------------------------------------------------------------
rng = random.Random(1337)
FREE_TEXTS = [
    "", "", "",
    "worked on a construction site for two years",
    "helped my uncle who is an electrician",
    "learned wiring at an ITI course",
    "did some wiring and lighting work on and off",
    "no formal training, learned on the job",
]
remaining = 100 - len(vectors)
for n in range(remaining):
    vec_id = f"L{idx:03d}"
    chosen = {}
    for item_id in ALL_ITEM_IDS:
        r = rng.random()
        if r < 0.33:
            chosen[item_id] = "never"
        elif r < 0.66:
            chosen[item_id] = "sometimes"
        else:
            chosen[item_id] = "often"
    add(vec_id, "mixed_random_seeded", {
        "answers": chosen,
        "free_text": rng.choice(FREE_TEXTS),
    })
    idx += 1

assert len(vectors) == 100, f"expected 100 vectors, built {len(vectors)}"

# Sanity: every required category is represented at least once (fails loudly if the
# generator above is edited in a way that silently drops a requirement).
categories = {v["category"] for v in vectors}
required_substrings = [
    "strong_ae", "temp_lighting_heavy", "lv_wiring_heavy", "db_mcb_panel_heavy",
    "domestic_only", "weak_coverage", "strong_safety", "weak_safety",
    "unrelated_plumber", "unrelated_mason", "unrelated_welder",
    "no_experience", "blank_missing", "contradictory",
    "hindi_input", "hinglish_input", "boundary_below_0_35", "boundary_at_or_above_0_35",
    "boundary_below_0_60", "boundary_at_or_above_0_60",
    "nos_absent_CON_N0602", "nos_absent_CON_N0603", "nos_absent_CON_N0604",
    "nos_absent_CON_N0605", "nos_absent_CON_N9001",
]
joined = " ".join(categories)
missing_reqs = [r for r in required_substrings if r not in joined]
assert not missing_reqs, f"generator dropped required categories: {missing_reqs}"

# Every T1-T5 task must be extra_evidence_needed=true in at least one vector.
tasks_flagged = set()
for v in vectors:
    for t in v["expected_output"]["applicable_tasks"]:
        if t["extra_evidence_needed"]:
            tasks_flagged.add(t["task"])
assert tasks_flagged == {"T1", "T2", "T3", "T4", "T5"}, f"not all tasks flagged as gaps: {tasks_flagged}"

header = (
    "// Python/Kotlin match-rules@r3 golden-vector parity contract (100 vectors).\n"
    "// Generated by ml/mapping/generate_golden_vectors.py -- do not hand-edit; re-run the\n"
    "// generator after any mapping/*.json or matcher.py change and commit the new file.\n"
    "// Every expected_output was produced by running matcher.py itself (see that script's\n"
    "// module docstring on what a golden vector does/does not prove).\n"
)
with OUT_PATH.open("w", encoding="utf-8") as f:
    f.write(header)
    for v in vectors:
        f.write(json.dumps(v, ensure_ascii=False) + "\n")

print(f"wrote {len(vectors)} golden vectors to {OUT_PATH}")
