#!/usr/bin/env python3
"""Audit a qualification pack's traceability back to its pinned source PDF.

Usage: python tools/audit_qp_traceability.py <pack_dir>
Exit 0 if every check passes, exit 1 otherwise.

This is a stricter, source-integrity-focused companion to pack_validate.py
(which checks budgets/anchors/task-links). This script checks:

  [source]   qp_code/qp_version in qp.json, tasks.json, rubric.json and
             every mapping/*.json file match source.json exactly
  [nos]      every required NOS code is present, none missing/extra
  [pcids]    no duplicate PC id within a NOS, no duplicate full PC id overall
  [text]     every PC's text is a non-empty string
  [pages]    every NOS and every PC carries source_page + source_reference
  [refs]     every PC id referenced from tasks.json, rubric.json and
             mapping/links.json resolves to a real PC in qp.json
  [coverage] coverage_matrix.json matches qp.json/tasks.json and no PC in a
             practical NOS is NOT_ASSESSED_IN_MVP (fails the build if a
             practical PC has no T1-T5 task coverage)
  [decl]     every NOS listed in mapping/thresholds.json's
             practical_nos_for_matching has >= 1 card/tool link in
             mapping/links.json (catches a scored NOS silently missing a
             declaration signal, e.g. the CON/N9001 gap found at Q-1
             completion where Safety/T1 never appeared in match output)
  [contract] mapping/links.json has EXACTLY the card_count/tool_count pinned
             in mapping/thresholds.json's declaration_contract (catches an
             edit that silently grows the worker-facing declaration past the
             approved 20-card + 6-tool worker-flow design), no duplicate
             card/tool ids, and no card/tool is linked to CON/N8001 or
             CON/N8002 (those two NOS are out of declaration scope by design
             under match-rules@r3, not an oversight -- see links.json status)
  [safety]   every task in tasks.json has step_guide[0] equal to
             tasks.json's own safety_first_step verbatim, and no step_guide
             anywhere in tasks.json contains an unsafe-electrical-work phrase
             (catches wording that implies a worker should energise a live
             training-board circuit -- see docs/gates/P3.md)
"""
import argparse
import json
import sys
from pathlib import Path

# The 8 compulsory NOS of CON/Q0602 v4.0 (qp_v4.0.pdf contents page, p.2).
# A pinned pack must contain exactly this set -- not a subset, not extras
# borrowed from a different QP or a different version of this QP.
REQUIRED_NOS = {
    "CON/N0602", "CON/N0603", "CON/N0604", "CON/N0605",
    "CON/N9001", "CON/N8001", "CON/N8002", "DGT/VSQ/N0101",
}


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    return json.loads(path.read_text())


def check_source_versions(pack_dir: Path, source: dict):
    mismatches = []
    files = {
        "qp.json": pack_dir / "qp.json",
        "tasks.json": pack_dir / "tasks.json",
        "rubric.json": pack_dir / "rubric.json",
    }
    mapping_dir = pack_dir / "mapping"
    if mapping_dir.exists():
        files.update({f"mapping/{p.name}": p for p in sorted(mapping_dir.glob("*.json"))})

    checked = []
    for label, path in files.items():
        if not path.exists():
            mismatches.append(f"{label}: file missing")
            continue
        doc = json.loads(path.read_text())
        code_key = "qp_code"
        version_key = "qp_version" if "qp_version" in doc else "version"
        if code_key not in doc or version_key not in doc:
            mismatches.append(f"{label}: no qp_code/qp_version field to check")
            continue
        checked.append(label)
        if doc[code_key] != source["qp_code"]:
            mismatches.append(f"{label}: qp_code={doc[code_key]!r} != source.json {source['qp_code']!r}")
        if doc[version_key] != source["qp_version"]:
            mismatches.append(f"{label}: qp_version={doc[version_key]!r} != source.json {source['qp_version']!r}")

    if not mismatches:
        return True, f"[source] qp_code/qp_version match source.json across {len(checked)} files ✓"
    return False, "[source] " + "; ".join(mismatches) + " ✗"


def check_required_nos(qp: dict):
    present = {nos["code"] for nos in qp["nos"]}
    missing = REQUIRED_NOS - present
    extra = present - REQUIRED_NOS
    if not missing and not extra:
        return True, f"[nos]    all {len(REQUIRED_NOS)} required NOS present, none extra ✓"
    parts = []
    if missing:
        parts.append(f"missing: {', '.join(sorted(missing))}")
    if extra:
        parts.append(f"unexpected: {', '.join(sorted(extra))}")
    return False, "[nos]    " + "; ".join(parts) + " ✗"


def all_pcs(qp: dict):
    """Yield (nos, pc) for every PC in qp.json, in document order."""
    for nos in qp["nos"]:
        for el in nos["elements"]:
            for pc in el["performance_criteria"]:
                yield nos, pc


def check_duplicate_pc_ids(qp: dict):
    seen_full = {}
    dupes = []
    for nos, pc in all_pcs(qp):
        full_id = f"{nos['code']}.{pc['id']}"
        if full_id in seen_full:
            dupes.append(full_id)
        seen_full[full_id] = True
    if not dupes:
        return True, f"[pcids]  no duplicate PC ids across {len(seen_full)} PCs ✓"
    return False, f"[pcids]  duplicate PC id(s): {', '.join(dupes)} ✗"


def check_pc_text_nonempty(qp: dict):
    empty = [f"{nos['code']}.{pc['id']}" for nos, pc in all_pcs(qp) if not str(pc.get("text", "")).strip()]
    if not empty:
        return True, "[text]   every PC has non-empty text ✓"
    return False, f"[text]   empty PC text: {', '.join(empty)} ✗"


def check_source_pages(qp: dict):
    missing = []
    for nos in qp["nos"]:
        if not nos.get("source_page") or not str(nos.get("source_reference", "")).strip():
            missing.append(f"{nos['code']} (NOS-level)")
    for nos, pc in all_pcs(qp):
        full_id = f"{nos['code']}.{pc['id']}"
        if not pc.get("source_page") or not str(pc.get("source_reference", "")).strip():
            missing.append(full_id)
    if not missing:
        n = sum(1 for _ in all_pcs(qp))
        return True, f"[pages]  source_page + source_reference present on all {len(qp['nos'])} NOS and {n} PCs ✓"
    return False, f"[pages]  missing source_page/source_reference: {', '.join(missing)} ✗"


def check_cross_references(qp: dict, pack_dir: Path):
    valid = {f"{nos['code']}.{pc['id']}" for nos, pc in all_pcs(qp)}
    bad = []

    tasks_path = pack_dir / "tasks.json"
    if tasks_path.exists():
        tasks = json.loads(tasks_path.read_text())
        for t in tasks["tasks"]:
            for full_id in t.get("linked_pcs", []):
                if full_id not in valid:
                    bad.append(f"tasks.json:{t['id']} -> {full_id}")

    rubric_path = pack_dir / "rubric.json"
    if rubric_path.exists():
        rubric = json.loads(rubric_path.read_text())
        for item in rubric.get("items", []):
            if item["pc_id"] not in valid:
                bad.append(f"rubric.json -> {item['pc_id']}")

    links_path = pack_dir / "mapping" / "links.json"
    if links_path.exists():
        links = json.loads(links_path.read_text())
        for group in ("cards", "tools"):
            for item in links.get(group, []):
                for link in item.get("links", []):
                    full_id = f"{link['nos']}.{link['pc']}"
                    if full_id not in valid:
                        bad.append(f"mapping/links.json:{item['id']} -> {full_id}")

    if not bad:
        return True, "[refs]   every tasks/rubric/mapping PC reference resolves to a real PC ✓"
    return False, f"[refs]   unknown PC reference(s): {', '.join(bad)} ✗"


# PCs pinned to NOT_APPLICABLE_IN_MVP regardless of task linkage -- structurally
# impossible to demonstrate in this MVP (no equipment / no safe capture path),
# not an assessor judgement call. See docs/evidence_status_model.md.
NOT_APPLICABLE_PCS = {"CON/N0603.PC16"}


def check_coverage_matrix(qp: dict, tasks: dict, pack_dir: Path):
    """Every practical-NOS PC must be on the TASK_EVIDENCE_PATHWAY (a pack-design
    fact: a task exists that is SUPPOSED to evidence it -- NOT proof that it was
    actually demonstrated in any given assessment, see
    docs/evidence_status_model.md); every declaration-only-NOS PC must be
    DECLARATION_OR_ASSESSOR_NOTE; NOT_ASSESSED_IN_MVP must not occur anywhere
    in the pinned pack. Also recomputes the expected status per PC from
    qp.json/tasks.json and fails if coverage_matrix.json has drifted out of
    sync (stale regeneration), and checks that NOT_APPLICABLE_PCS carry
    mvp_applicability=NOT_APPLICABLE_IN_MVP (and no other PC does)."""
    matrix_path = pack_dir / "coverage_matrix.json"
    if not matrix_path.exists():
        return False, "[coverage] coverage_matrix.json missing ✗"
    matrix = json.loads(matrix_path.read_text())

    task_linked_pcs = set()
    for t in tasks["tasks"]:
        task_linked_pcs.update(t["linked_pcs"])

    expected = {}
    for nos, pc in all_pcs(qp):
        full_id = f"{nos['code']}.{pc['id']}"
        if full_id in task_linked_pcs:
            expected[full_id] = "TASK_EVIDENCE_PATHWAY"
        elif not nos["practical"]:
            expected[full_id] = "DECLARATION_OR_ASSESSOR_NOTE"
        else:
            expected[full_id] = "NOT_ASSESSED_IN_MVP"

    bad_status = []
    seen = set()
    for row in matrix.get("rows", []):
        pc_id = row["pc_id"]
        seen.add(pc_id)
        want = expected.get(pc_id, "UNKNOWN_PC")
        if row["status"] != want:
            bad_status.append(f"{pc_id}: matrix says {row['status']}, expected {want}")
        want_applicability = "NOT_APPLICABLE_IN_MVP" if pc_id in NOT_APPLICABLE_PCS else "ASSESSABLE"
        got_applicability = row.get("mvp_applicability")
        if got_applicability != want_applicability:
            bad_status.append(f"{pc_id}: mvp_applicability={got_applicability!r}, expected {want_applicability!r}")

    missing_rows = set(expected) - seen
    for pc_id in missing_rows:
        bad_status.append(f"{pc_id}: no row in coverage_matrix.json")

    not_assessed = [r["pc_id"] for r in matrix.get("rows", []) if r["status"] == "NOT_ASSESSED_IN_MVP"]
    if not_assessed:
        bad_status.append(f"practical PC(s) with NOT_ASSESSED_IN_MVP status: {', '.join(not_assessed)}")

    if not bad_status:
        counts = matrix.get("counts", {})
        return True, (f"[coverage] coverage_matrix.json matches qp.json/tasks.json, "
                       f"0 PCs NOT_ASSESSED_IN_MVP, mvp_applicability correct for "
                       f"{len(NOT_APPLICABLE_PCS)} NOT_APPLICABLE_IN_MVP PC(s) ✓ "
                       f"(TASK_EVIDENCE_PATHWAY={counts.get('TASK_EVIDENCE_PATHWAY', 0)}, "
                       f"DECLARATION_OR_ASSESSOR_NOTE={counts.get('DECLARATION_OR_ASSESSOR_NOTE', 0)})")
    return False, "[coverage] " + "; ".join(bad_status) + " ✗"


def check_declaration_coverage(pack_dir: Path):
    """Every NOS the matcher actually scores (thresholds.practical_nos_for_matching)
    must have >= 1 card/tool link in mapping/links.json. A practical NOS with zero
    declaration signals silently gets coverage=0 / has_experience=False for every
    worker forever (see match_rules@r1 -> r2: CON/N9001 had no cards at all, so T1
    never appeared in applicable_tasks even though it's a real, task-evidenced NOS)."""
    thresholds_path = pack_dir / "mapping" / "thresholds.json"
    links_path = pack_dir / "mapping" / "links.json"
    if not thresholds_path.exists() or not links_path.exists():
        return False, "[decl]   mapping/thresholds.json or mapping/links.json missing ✗"

    thresholds = json.loads(thresholds_path.read_text())
    links = json.loads(links_path.read_text())

    linked_nos = set()
    for group in ("cards", "tools"):
        for item in links.get(group, []):
            for link in item.get("links", []):
                linked_nos.add(link["nos"])

    scored_nos = [e["nos"] for e in thresholds.get("practical_nos_for_matching", [])]
    missing = [nos for nos in scored_nos if nos not in linked_nos]
    if not missing:
        return True, (f"[decl]   every scored NOS ({len(scored_nos)}) has >= 1 declaration "
                       f"card/tool link ✓")
    return False, f"[decl]   scored NOS with zero declaration signals: {', '.join(missing)} ✗"


def check_declaration_contract(pack_dir: Path):
    """Enforce the exact 20-card + 6-tool worker-flow contract pinned in
    thresholds.json.declaration_contract. Fails loudly on: a count drift,
    a duplicate card/tool id, or any link that reaches CON/N8001/CON/N8002
    (those two NOS were deliberately dropped from the declaration's scope
    in the r2->r3 reduction -- a link reappearing would silently reintroduce
    a declaration_only side-channel this project decided to remove)."""
    thresholds_path = pack_dir / "mapping" / "thresholds.json"
    links_path = pack_dir / "mapping" / "links.json"
    if not thresholds_path.exists() or not links_path.exists():
        return False, "[contract] mapping/thresholds.json or mapping/links.json missing ✗"

    thresholds = json.loads(thresholds_path.read_text())
    links = json.loads(links_path.read_text())
    contract = thresholds.get("declaration_contract", {})
    want_cards = contract.get("card_count")
    want_tools = contract.get("tool_count")
    if want_cards is None or want_tools is None:
        return False, "[contract] thresholds.json missing declaration_contract.card_count/tool_count ✗"

    cards = links.get("cards", [])
    tools = links.get("tools", [])
    problems = []
    if len(cards) != want_cards:
        problems.append(f"card_count={len(cards)}, expected {want_cards}")
    if len(tools) != want_tools:
        problems.append(f"tool_count={len(tools)}, expected {want_tools}")

    card_ids = [c["id"] for c in cards]
    tool_ids = [t["id"] for t in tools]
    dupe_cards = sorted({i for i in card_ids if card_ids.count(i) > 1})
    dupe_tools = sorted({i for i in tool_ids if tool_ids.count(i) > 1})
    if dupe_cards:
        problems.append(f"duplicate card id(s): {', '.join(dupe_cards)}")
    if dupe_tools:
        problems.append(f"duplicate tool id(s): {', '.join(dupe_tools)}")

    out_of_scope_nos = {"CON/N8001", "CON/N8002"}
    leaked = sorted({
        f"{item['id']} -> {link['nos']}"
        for group in (cards, tools)
        for item in group
        for link in item.get("links", [])
        if link["nos"] in out_of_scope_nos
    })
    if leaked:
        problems.append(f"link(s) to out-of-scope NOS: {', '.join(leaked)}")

    if not problems:
        return True, (f"[contract] exactly {want_cards} cards + {want_tools} tools, no duplicate "
                       f"ids, no CON/N8001/CON/N8002 links ✓")
    return False, "[contract] " + "; ".join(problems) + " ✗"


# Electrical-work phrases that must never appear in a step_guide, matched as a
# case-insensitive substring. These are deliberately the exact unsafe phrases
# found and removed during the P-3 safety fix (see docs/gates/P3.md) -- a
# regression guard, not a general "contains the word energise" filter, since
# the REQUIRED safe wording itself legitimately contains words like "energise"
# and "supply" inside a negation ("Do not energise the board yourself"; "Do
# not reconnect the supply yourself"). A substring filter can't distinguish an
# instruction from its own negation, so this list only holds phrases that are
# unsafe in both polarities.
UNSAFE_PHRASES = (
    "live-ready", "power check confirming the fix", "tag the board as live", "live tag",
)


def check_task_safety_wording(pack_dir: Path, tasks: dict):
    """Every task's step_guide[0] must equal tasks.json's own safety_first_step
    verbatim (not a paraphrase -- a paraphrase could silently drop "isolated"
    or "de-energised" or the tester-first requirement), and no step anywhere
    may contain an UNSAFE_PHRASES entry."""
    safety_first_step = tasks.get("safety_first_step")
    if not safety_first_step:
        return False, "[safety] tasks.json missing top-level safety_first_step ✗"

    problems = []
    for t in tasks["tasks"]:
        guide = t.get("step_guide", [])
        if not guide or guide[0] != safety_first_step:
            problems.append(f"{t['id']}: step_guide[0] != safety_first_step verbatim")
        for step in guide:
            lowered = step.lower()
            for phrase in UNSAFE_PHRASES:
                if phrase in lowered:
                    problems.append(f"{t['id']}: unsafe phrase '{phrase}' found in step_guide")

    if not problems:
        return True, (f"[safety] all {len(tasks['tasks'])} tasks start with the safety_first_step "
                       f"verbatim, no unsafe phrase present ✓")
    return False, "[safety] " + "; ".join(problems) + " ✗"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pack_dir", type=Path)
    args = ap.parse_args()
    pack_dir: Path = args.pack_dir

    try:
        source = load_json(pack_dir / "source.json")
        qp = load_json(pack_dir / "qp.json")
        tasks = load_json(pack_dir / "tasks.json")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[pack]  failed to load pack at {pack_dir}: {e} ✗")
        sys.exit(1)

    checks = [
        check_source_versions(pack_dir, source),
        check_required_nos(qp),
        check_duplicate_pc_ids(qp),
        check_pc_text_nonempty(qp),
        check_source_pages(qp),
        check_cross_references(qp, pack_dir),
        check_coverage_matrix(qp, tasks, pack_dir),
        check_declaration_coverage(pack_dir),
        check_declaration_contract(pack_dir),
        check_task_safety_wording(pack_dir, tasks),
    ]

    failed = 0
    for ok, line in checks:
        print(line)
        if not ok:
            failed += 1

    if failed:
        print(f"--- {failed} check(s) failed --- exit 1")
        sys.exit(1)


if __name__ == "__main__":
    main()
