"""Basic seed data for a demo assessor queue: one assessor, three workers,
three assessments (draft / submitted / in_review) against the imported
ae-con-q0602 pack. Run after pack_import.

Usage: python -m server.app.seed
"""
from pathlib import Path

from sqlalchemy.orm import Session

from . import models
from .db import SessionLocal
from .pack_import import import_pack_cli

REPO_ROOT = Path(__file__).resolve().parents[2]


def seed(db: Session) -> None:
    pack = import_pack_cli(REPO_ROOT / "packs" / "ae-con-q0602", db)

    assessor = db.query(models.User).filter_by(role="assessor", email="assessor.demo@parakh.test").one_or_none()
    if assessor is None:
        assessor = models.User(role="assessor", display_name="Demo Assessor", email="assessor.demo@parakh.test")
        db.add(assessor)
        db.flush()

    workers = []
    for i, phone in enumerate(["9000000001", "9000000002", "9000000003"], start=1):
        w = db.query(models.User).filter_by(phone=phone).one_or_none()
        if w is None:
            w = models.User(role="worker", display_name=f"Demo Worker {i}", phone=phone)
            db.add(w)
            db.flush()
        workers.append(w)

    templates = db.query(models.TaskTemplate).filter_by(pack_id=pack.id).order_by(models.TaskTemplate.task_order).all()

    statuses = ["draft", "submitted", "in_review"]
    for worker, status in zip(workers, statuses):
        existing = db.query(models.Assessment).filter_by(worker_id=worker.id, pack_id=pack.id).one_or_none()
        if existing:
            continue
        assessment = models.Assessment(
            worker_id=worker.id, pack_id=pack.id, status=status,
            assessor_id=assessor.id if status != "draft" else None,
        )
        db.add(assessment)
        db.flush()
        for t in templates:
            db.add(models.AssessmentTask(assessment_id=assessment.id, task_code=t.task_code, budget_bytes=t.budget_bytes))

    db.commit()
    print(f"seeded: pack={pack.qp_code} assessor={assessor.email} workers={len(workers)}")


if __name__ == "__main__":
    session = SessionLocal()
    try:
        seed(session)
    finally:
        session.close()
