#!/usr/bin/env python3
"""Deterministic, rule-based CON/Q0602 declaration matcher (match-rules@r1).

Pure stdlib, no model weights: this is the Python reference implementation of
the rules in packs/ae-con-q0602/mapping/{links,keywords,thresholds}.json. The
Kotlin port (on-device, phase P3) must agree with this file on every golden
vector at IC-1 — see the master plan §4.2 and §7.

The matcher never decides competence. It only explains how a self-declaration
relates to CON/Q0602 and which tasks need the most evidence.
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
    """declaration = {"answers": {item_id: "often"|"sometimes"|"never", ...}, "free_text": "..."}"""
    thresholds = rules["thresholds"]
    keywords = rules["keywords"]
    answers = declaration.get("answers", {})
    free_text = declaration.get("free_text", "")

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
        pcs = nos_pcs.get(nos, set())
        claims = [pc_claim.get(f"{nos}.{pc}", 0.0) for pc in pcs]
        coverage = sum(claims) / len(claims) if claims else 0.0
        nos_coverage[nos] = coverage
        nos_experience[nos] = any(c > 0 for c in claims)

    total_credits = sum(e["credits"] for e in thresholds["practical_nos_for_matching"])
    overall = sum(nos_coverage[e["nos"]] * e["credits"] for e in thresholds["practical_nos_for_matching"]) / total_credits

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

    return {
        "match_result": result,
        "overall_coverage": round(overall, 4),
        "nos_coverage": {nos: round(c, 4) for nos, c in nos_coverage.items()},
        "nos_has_experience": nos_experience,
        "because": because,
        "gap_nos": gap_nos,
        "applicable_tasks": applicable_tasks,
        "rules_version": rules["thresholds"]["match_rules_id"],
    }
