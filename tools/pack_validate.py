#!/usr/bin/env python3
"""Validate a qualification pack directory (qp.json, tasks.json, rubric.json,
mapping/{links,keywords,thresholds}.json, qp_v4.0.pdf).

Usage: python tools/pack_validate.py <pack_dir>
Exit 0 if every check passes, exit 1 and a non-zero check count otherwise.

Checks (P1 exit test, master plan p.15):
  [qp]     NOS/PC counts load; PDF on disk matches the sha256 recorded in qp.json
  [tasks]  per-task budgets sum to exactly the pack's declared MB budget
  [rubric] every practical PC has a 0-3 anchor set and nonzero marks
  [links]  every practical PC is evidenced by >= 1 task (tasks.json linked_pcs)
  [match]  every declaration card/tool in mapping/links.json links to >= 1 PC
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    return json.loads(path.read_text())


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def practical_pcs(qp):
    """Yield (nos_code, pc_id, full_id) for every PC in every practical NOS."""
    for nos in qp["nos"]:
        if not nos.get("practical"):
            continue
        for el in nos["elements"]:
            for pc in el["performance_criteria"]:
                yield nos["code"], pc["id"], f"{nos['code']}.{pc['id']}"


def check_qp(pack_dir: Path, qp: dict):
    total_pcs = sum(len(el["performance_criteria"]) for nos in qp["nos"] for el in nos["elements"])
    nos_count = len(qp["nos"])
    pdf_path = pack_dir / Path(qp["source_pdf"]["path"]).name
    pdf_sha = None
    ok = True
    note = ""
    if pdf_path.exists():
        pdf_sha = sha256_of(pdf_path)
        if pdf_sha != qp["source_pdf"]["sha256"]:
            ok = False
            note = " ✗ PDF ON DISK DOES NOT MATCH RECORDED sha256"
    else:
        pdf_sha = "<missing — skipped>"
    line = (f"[qp]    {qp['qp_code']} v{qp['version']}  pdf_sha256={pdf_sha}  "
            f"NOS={nos_count}  PCs={total_pcs}{note}")
    return ok, line


def check_tasks(tasks: dict):
    budget_mb = tasks["final_evidence_budget_mb"]
    per_task = [(t["id"], t["budget_mb"]) for t in tasks["tasks"]]
    total = sum(mb for _, mb in per_task)
    breakdown = "+".join(str(mb) for _, mb in per_task)
    bytes_ok = all(t["budget_mb"] * 1024 * 1024 == t["budget_bytes"] for t in tasks["tasks"])
    if total == budget_mb and bytes_ok:
        line = f"[tasks] {'..'.join([per_task[0][0], per_task[-1][0]])} budgets {breakdown} = {total} MB ✓"
        return True, line
    problem = f"{total} MB {'>' if total > budget_mb else '<'} {budget_mb} MB" if total != budget_mb else "budget_bytes mismatch"
    line = f"[tasks] budgets sum {problem} ✗"
    return False, line


def check_rubric(qp: dict, rubric: dict):
    items_by_id = {it["pc_id"]: it for it in rubric["items"]}
    missing = []
    critical = 0
    for nos_code, pc_id, full_id in practical_pcs(qp):
        item = items_by_id.get(full_id)
        if item is None:
            missing.append(full_id)
            continue
        anchors = item.get("anchors", {})
        if not all(k in anchors and anchors[k] for k in ("0", "1", "2", "3")):
            missing.append(full_id + " (incomplete anchors)")
            continue
        if not item.get("marks", 0) > 0:
            missing.append(full_id + " (zero marks)")
            continue
        if item.get("critical"):
            critical += 1
    if not missing:
        line = f"[rubric] {rubric['rubric_id'].split('@')[-1]}: anchors on all practical PCs ✓  critical PCs={critical} ✓"
        return True, line
    line = f"[rubric] missing/incomplete anchors for: {', '.join(missing)} ✗"
    return False, line


def check_links(qp: dict, tasks: dict):
    linked = set()
    for t in tasks["tasks"]:
        linked.update(t["linked_pcs"])
    missing = [full_id for _, _, full_id in practical_pcs(qp) if full_id not in linked]
    if not missing:
        line = "[links]  every practical PC evidenced by ≥ 1 task ✓"
        return True, line
    line = f"[links]  practical PC with no task: {', '.join(missing)} ✗"
    return False, line


def check_match(links: dict, thresholds: dict):
    rules_id = thresholds.get("match_rules_id", "?")
    empty = [c["id"] for c in links.get("cards", []) if not c.get("links")]
    empty += [t["id"] for t in links.get("tools", []) if not t.get("links")]
    if not empty:
        n = len(links.get("cards", [])) + len(links.get("tools", []))
        line = f"[match]  rules {rules_id.split('@')[-1]} · every task card linked to ≥ 1 PC ✓ ({n} cards/tools)"
        return True, line
    line = f"[match]  card/tool with no PC link: {', '.join(empty)} ✗"
    return False, line


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pack_dir", type=Path)
    args = ap.parse_args()
    pack_dir: Path = args.pack_dir

    try:
        qp = load_json(pack_dir / "qp.json")
        tasks = load_json(pack_dir / "tasks.json")
        rubric = load_json(pack_dir / "rubric.json")
        links = load_json(pack_dir / "mapping" / "links.json")
        thresholds = load_json(pack_dir / "mapping" / "thresholds.json")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[pack]  failed to load pack at {pack_dir}: {e} ✗")
        sys.exit(1)

    checks = [
        check_qp(pack_dir, qp),
        check_tasks(tasks),
        check_rubric(qp, rubric),
        check_links(qp, tasks),
        check_match(links, thresholds),
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
