#!/usr/bin/env python3
"""Python-side half of the Python/Kotlin golden-vector parity check (master
plan p.8: "Python (server) and Kotlin (phone) implement the same rules and
must agree on all 100 golden vectors"). The Kotlin matcher port is a P3
deliverable and does not exist in this repo yet -- this test cannot check
cross-language agreement before that exists. What it checks today: the
Python matcher is deterministic and its output for all 100 vectors in
golden_vectors.jsonl is pinned to what's recorded there, so a future Kotlin
port -- or a future refactor of matcher.py itself -- has a concrete,
reproducible target to agree with (see test_matcher.py for the structural
assertions that currently serve as substitutes).

Run: python3 ml/mapping/test_golden_vectors.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from matcher import load_rules, match  # noqa: E402

ROOT = Path(__file__).parent.parent.parent
RULES = load_rules(ROOT / "packs/ae-con-q0602/mapping")
VECTORS_PATH = Path(__file__).parent / "golden_vectors.jsonl"


def load_vectors():
    vectors = []
    with VECTORS_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            vectors.append(json.loads(line))
    return vectors


def test_all_vectors_reproduce_exactly():
    vectors = load_vectors()
    assert len(vectors) == 100, f"expected 100 golden vectors, found {len(vectors)}"
    mismatches = []
    for v in vectors:
        got = match(v["input"], RULES)
        if got != v["expected_output"]:
            mismatches.append(v["id"])
    assert not mismatches, f"matcher output drifted from golden_vectors.jsonl for: {mismatches}"


def test_matcher_is_deterministic():
    vectors = load_vectors()
    for v in vectors[:10]:
        a = match(v["input"], RULES)
        b = match(v["input"], RULES)
        assert a == b, f"{v['id']}: matcher is not deterministic across repeated calls"


if __name__ == "__main__":
    test_all_vectors_reproduce_exactly()
    test_matcher_is_deterministic()
    print(f"ml/mapping/test_golden_vectors.py: all 100 golden vectors reproduce exactly, matcher is deterministic")
