#!/usr/bin/env python3
"""Deterministic, rule-based CON/Q0602 declaration matcher (match-rules@r2).

Pure stdlib, no model weights: this is the Python reference implementation of
the rules in packs/ae-con-q0602/mapping/{links,keywords,thresholds}.json. The
Kotlin port (apps/android/core/mapping, phase P3) must agree with this file on
every golden vector in ml/mapping/golden_vectors.jsonl — see
docs/gates/IC1A.md and the master plan §4.2/§7.

The matcher never decides competence. It only explains how a self-declaration
relates to CON/Q0602 and which tasks need the most evidence. It also never
claims independent assessor agreement — see docs/gates/IC1A.md for the
technical-only acceptance criteria this file is held to.
"""
import json
from pathlib import Path


def load_rules(mapping_dir: Path) -> dict:
    links = json.loads((mapping_dir / "links.json").read_text())
    keywords = json.loads((mapping_dir / "keywords.json").read_text())
    thresholds = json.loads((mapping_dir / "thresholds.json").read_text())
    tasks_path = mapping_dir.parent / "tasks.json"
    nos_task = {}
    if tasks_path.exists():
        tasks = json.loads(tasks_path.read_text())
        nos_task = {t["nos"]: t["id"] for t in tasks["tasks"]}
    return {"links": links, "keywords": keywords, "thresholds": thresholds, "nos_task": nos_task}


def _declaration_items(rules: dict):
    """All (item_id, links) pairs across declaration cards and the tool grid."""
    for c in rules["links"].get("cards", []):
        yield c["id"], c["links"]
    for t in rules["links"].get("tools", []):
        yield t["id"], t["links"]


def _known_item_ids(rules: dict) -> set:
    return {item_id for item_id, _ in _declaration_items(rules)}


def normalize_declaration(declaration) -> dict:
    """Accept either the canonical dict form
    {"answers": {item_id: "often"|"sometimes"|"never"}, "free_text": "..."}
    or a list-keyed form {"answers": [{"item_id": ..., "answer": ...}, ...],
    "free_text": "..."} (e.g. what a UI layer that iterates form fields might
    naturally produce), and return the canonical dict form. Raises ValueError
    with a clear, specific message on any malformed input — this is the only
    place declaration shape is validated structurally; validate_declaration()
    below validates the *values* once the shape is known-good.
    """
    if not isinstance(declaration, dict):
        raise ValueError(f"declaration must be an object, got {type(declaration).__name__}")

    answers = declaration.get("answers", {})
    if isinstance(answers, list):
        normalized: dict = {}
        seen_ids: set = set()
        for i, rec in enumerate(answers):
            if not isinstance(rec, dict) or "item_id" not in rec or "answer" not in rec:
                raise ValueError(
                    f"declaration['answers'][{i}] must be an object with 'item_id' and 'answer' keys, got {rec!r}"
                )
            item_id = rec["item_id"]
            if item_id in seen_ids:
                raise ValueError(f"duplicate declaration item_id in answers list: {item_id!r}")
            seen_ids.add(item_id)
            normalized[item_id] = rec["answer"]
        answers = normalized
    elif isinstance(answers, dict):
        pass
    else:
        raise ValueError(
            f"declaration['answers'] must be an object or a list, got {type(answers).__name__}"
        )

    free_text = declaration.get("free_text", "")
    if free_text is None:
        free_text = ""
    if not isinstance(free_text, str):
        raise ValueError(f"declaration['free_text'] must be a string, got {type(free_text).__name__}")

    return {"answers": answers, "free_text": free_text}


def validate_declaration(declaration: dict, rules: dict) -> None:
    """Validate a *normalized* declaration's values against the pinned rules.
    Raises ValueError with a message naming every offending id/value (not
    just the first) so a caller can show the worker/UI everything wrong in
    one pass. Call normalize_declaration() first if the input might be in
    the list-keyed form.
    """
    known_ids = _known_item_ids(rules)
    valid_answers = set(rules["thresholds"]["answer_strength"].keys())

    unknown = sorted(set(declaration["answers"]) - known_ids)
    if unknown:
        raise ValueError(
            f"unknown declaration item id(s): {', '.join(unknown)} "
            f"(not a card or tool defined in mapping/links.json)"
        )

    bad_values = sorted(
        f"{item_id}={answer!r}"
        for item_id, answer in declaration["answers"].items()
        if answer not in valid_answers
    )
    if bad_values:
        raise ValueError(
            f"unsupported claim strength for: {', '.join(bad_values)} "
            f"(must be one of {sorted(valid_answers)})"
        )


def _compensated_sum(values) -> float:
    """Neumaier (improved Kahan) compensated summation.

    CPython's builtin sum() has used a compensated-summation variant for
    float addition since 3.12, which is MORE ACCURATE than naive sequential
    `total += v` -- but that accuracy gain is exactly what broke Python/Kotlin
    parity here: Kotlin's stdlib `Iterable<Double>.sum()` is naive and can
    land one ULP away from CPython's sum() on the same inputs, which is
    enough to flip a value sitting on a round-half boundary (e.g. 0.05625
    rounding to 0.0562 vs 0.0563 -- the actual bug this function fixes; see
    git history / docs/gates/Q1.md). Implementing the SAME explicit algorithm
    here and in Matcher.kt's compensatedSum() makes the result depend on our
    own auditable code, not on a Python-version-specific stdlib internal.
    """
    total = 0.0
    c = 0.0
    for v in values:
        t = total + v
        if abs(total) >= abs(v):
            c += (total - t) + v
        else:
            c += (v - t) + total
        total = t
    return total + c


def _answer_strength(thresholds: dict, answer: str) -> float:
    return thresholds["answer_strength"].get(answer, 0.0)


def _keyword_hit(keywords: dict, item_id: str, free_text: str) -> bool:
    if not free_text:
        return False
    entry = keywords.get("cards", {}).get(item_id)
    if not entry:
        return False
    text = free_text.lower()
    for terms in entry.values():
        for term in terms:
            if term.lower() in text:
                return True
    return False


def match(declaration: dict, rules: dict) -> dict:
    """declaration = {"answers": {item_id: "often"|"sometimes"|"never", ...}, "free_text": "..."}
    (or the list-keyed form accepted by normalize_declaration). Raises
    ValueError on malformed input, unknown card/tool ids, or unsupported
    claim-strength values — see normalize_declaration/validate_declaration.
    """
    declaration = normalize_declaration(declaration)
    validate_declaration(declaration, rules)

    thresholds = rules["thresholds"]
    keywords = rules["keywords"]
    answers = declaration["answers"]
    free_text = declaration["free_text"]

    # effective_claim per PC = max over links touching it of (answer_strength x link.weight)
    pc_claim: dict[str, float] = {}
    pc_sources: dict[str, list[str]] = {}
    for item_id, item_links in _declaration_items(rules):
        base = _answer_strength(thresholds, answers.get(item_id, "never"))
        if base < 0.6 and _keyword_hit(keywords, item_id, free_text):
            base = max(base, 0.6)
        if base <= 0:
            continue
        for link in item_links:
            full_pc = f"{link['nos']}.{link['pc']}"
            contribution = base * link["weight"]
            if contribution > pc_claim.get(full_pc, 0.0):
                pc_claim[full_pc] = contribution
                pc_sources[full_pc] = [item_id]
            elif contribution == pc_claim.get(full_pc, 0.0):
                pc_sources.setdefault(full_pc, []).append(item_id)

    # PCs in scope per NOS = every PC referenced by >= 1 link for that NOS (links.json defines scope)
    nos_pcs: dict[str, set] = {}
    for item_id, item_links in _declaration_items(rules):
        for link in item_links:
            nos_pcs.setdefault(link["nos"], set()).add(link["pc"])

    nos_coverage = {}
    nos_experience = {}
    for entry in thresholds["practical_nos_for_matching"]:
        nos = entry["nos"]
        # sorted(): Python set iteration order is hash-seed-dependent (PYTHONHASHSEED
        # randomization is on by default since 3.3) and, separately, differs in
        # general from Kotlin's LinkedHashSet insertion order. Floating-point sum()
        # is not associative, so an unsorted iteration order can make this matcher
        # non-deterministic ACROSS PROCESSES (not just non-identical to Kotlin) --
        # sorting pins one specific, language-independent summation order.
        pcs = sorted(nos_pcs.get(nos, set()))
        claims = [pc_claim.get(f"{nos}.{pc}", 0.0) for pc in pcs]
        coverage = _compensated_sum(claims) / len(claims) if claims else 0.0
        nos_coverage[nos] = coverage
        nos_experience[nos] = any(c > 0 for c in claims)

    total_credits = sum(e["credits"] for e in thresholds["practical_nos_for_matching"])  # ints, exact
    overall = _compensated_sum(
        nos_coverage[e["nos"]] * e["credits"] for e in thresholds["practical_nos_for_matching"]
    ) / total_credits

    all_have_experience = all(nos_experience.values())
    if overall >= 0.60 and all_have_experience:
        result = "appropriate_match"
    elif overall >= 0.35:
        result = "partial_match"
    else:
        result = "not_appropriate_match"

    gap_nos = [nos for nos in nos_coverage if nos_coverage[nos] < 0.60 or not nos_experience[nos]]

    because = []
    for entry in thresholds["practical_nos_for_matching"]:
        nos = entry["nos"]
        if not nos_experience[nos]:
            because.append(f"{nos}: no declared experience on any linked card/tool")
        else:
            because.append(f"{nos}: coverage {nos_coverage[nos]:.2f} from {entry['credits']} credits")

    applicable_tasks = []
    for entry in thresholds["practical_nos_for_matching"]:
        nos = entry["nos"]
        task_id = rules["nos_task"].get(nos)
        applicable_tasks.append({
            "task": task_id,
            "nos": nos,
            "extra_evidence_needed": nos in gap_nos,
        })

    # Declaration-only NOS (CON/N8001 teamwork, CON/N8002 plan & organise): linked and
    # surfaced for worker/assessor context, but NEVER read by overall_coverage, nos_coverage,
    # match_result or gap_nos above -- these are generic employability behaviours, not
    # Assistant-Electrician trade skill (thresholds.json.declaration_only_nos).
    declaration_only_signals = []
    for entry in thresholds.get("declaration_only_nos", []):
        nos = entry["nos"]
        pcs = nos_pcs.get(nos, set())
        matched_items: set = set()
        has_experience = False
        for pc in pcs:
            full_pc = f"{nos}.{pc}"
            if pc_claim.get(full_pc, 0.0) > 0:
                has_experience = True
                matched_items.update(pc_sources.get(full_pc, []))
        label = entry.get("label", nos)
        if has_experience:
            because_line = f"{nos} ({label}): worker declared relevant experience — informational only, not scored"
        else:
            because_line = f"{nos} ({label}): no declared experience — informational only, not scored"
        declaration_only_signals.append({
            "nos": nos,
            "label": label,
            "has_declared_experience": has_experience,
            "matched_items": sorted(matched_items),
            "because": because_line,
        })

    return {
        "match_result": result,
        "overall_coverage": round(overall, 4),
        "nos_coverage": {nos: round(c, 4) for nos, c in nos_coverage.items()},
        "nos_has_experience": nos_experience,
        "because": because,
        "gap_nos": gap_nos,
        "applicable_tasks": applicable_tasks,
        "declaration_only_signals": declaration_only_signals,
        "rules_version": rules["thresholds"]["match_rules_id"],
    }
