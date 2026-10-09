"""Import a qualification pack (packs/<name>/) into the database.

Assumes the pack already passes tools/pack_validate.py and
tools/audit_qp_traceability.py -- run those first (import_pack_cli does).
This does not re-validate budgets/anchors/traceability; it only loads
already-trustworthy pack data into SQL tables.
"""
import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from . import models

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(pack_dir: Path, name: str) -> dict:
    return json.loads((pack_dir / name).read_text())


def import_pack(db: Session, pack_dir: Path) -> models.QualificationPack:
    qp = _load(pack_dir, "qp.json")
    tasks_doc = _load(pack_dir, "tasks.json")
    rubric_doc = _load(pack_dir, "rubric.json")

    existing = (
        db.query(models.QualificationPack)
        .filter_by(qp_code=qp["qp_code"], qp_version=qp["version"], pack_version=rubric_doc["rubric_id"])
        .one_or_none()
    )
    if existing:
        return existing

    pack = models.QualificationPack(
        qp_code=qp["qp_code"],
        qp_version=qp["version"],
        pack_version=rubric_doc["rubric_id"],
        qp_name=qp["qp_name"],
        source_pdf_sha256=qp["source_pdf"]["sha256"],
        source_pdf_path=qp["source_pdf"]["path"],
        minimum_aggregate_passing_percent=qp["minimum_aggregate_passing_percent"],
        final_evidence_budget_bytes=tasks_doc["final_evidence_budget_bytes"],
    )
    db.add(pack)
    db.flush()

    for task in tasks_doc["tasks"]:
        db.add(models.TaskTemplate(
            pack_id=pack.id,
            task_code=task["id"],
            title=task["title"],
            nos_code=task["nos"],
            budget_bytes=task["budget_bytes"],
            evidence_hint=task["evidence_hint"],
            step_guide=task["step_guide"],
            linked_pcs=task["linked_pcs"],
            task_order=int(task["id"][1:]),
        ))

    rubric_by_pc = {item["pc_id"]: item for item in rubric_doc["items"]}

    for nos_doc in qp["nos"]:
        nos = models.NOS(
            pack_id=pack.id,
            code=nos_doc["code"],
            title=nos_doc["title"],
            credits=nos_doc["credits"],
            theory_marks=nos_doc["theory_marks"],
            practical_marks=nos_doc["practical_marks"],
            weightage=nos_doc["weightage"],
            practical=nos_doc["practical"],
            assessed_via=nos_doc["assessed_via"],
            task_code=nos_doc.get("task"),
            source_page=nos_doc["source_page"],
            source_reference=nos_doc["source_reference"],
        )
        db.add(nos)
        db.flush()

        for element in nos_doc["elements"]:
            for pc_doc in element["performance_criteria"]:
                full_id = f"{nos_doc['code']}.{pc_doc['id']}"
                rubric_entry = rubric_by_pc.get(full_id)
                pathway = rubric_entry["evidence_pathway"] if rubric_entry else (
                    "DECLARATION_OR_ASSESSOR_NOTE" if not nos_doc["practical"] else "NOT_ASSESSED_IN_MVP"
                )
                applicability = rubric_entry["mvp_applicability"] if rubric_entry else "ASSESSABLE"

                pc = models.PerformanceCriterion(
                    nos_id=nos.id,
                    pc_code=pc_doc["id"],
                    full_id=full_id,
                    text=pc_doc["text"],
                    source_page=pc_doc["source_page"],
                    source_reference=pc_doc["source_reference"],
                    evidence_pathway=pathway,
                    mvp_applicability=applicability,
                )
                db.add(pc)
                db.flush()

                if rubric_entry:
                    db.add(models.RubricItem(
                        pc_id=pc.id,
                        rubric_version=rubric_doc["rubric_id"],
                        marks=rubric_entry["marks"],
                        critical=rubric_entry["critical"],
                        anchors=rubric_entry["anchors"],
                        disclaimer=rubric_entry["disclaimer"],
                        evidence_hint=rubric_entry["evidence_hint"],
                    ))

    db.commit()
    db.refresh(pack)
    return pack


def import_pack_cli(pack_dir: Path, db: Session) -> models.QualificationPack:
    """Re-validates the pack with P1's tooling before importing."""
    for script in ("tools/pack_validate.py", "tools/audit_qp_traceability.py"):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / script), str(pack_dir)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"{script} failed for {pack_dir}, refusing to import:\n{result.stdout}{result.stderr}")
    return import_pack(db, pack_dir)


if __name__ == "__main__":
    from .db import SessionLocal

    pack_path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "packs" / "ae-con-q0602"
    session = SessionLocal()
    try:
        imported = import_pack_cli(pack_path, session)
        print(f"imported {imported.qp_code} {imported.qp_version} ({imported.pack_version}) id={imported.id}")
    finally:
        session.close()
