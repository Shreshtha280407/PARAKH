"""Basic seed data for a demo assessor queue: one assessor, three workers,
three assessments (draft / submitted / in_review) against the imported
ae-con-q0602 pack. Run after pack_import.

Usage: python -m server.app.seed (local) / python -m app.seed (in Docker)

The dev assessor's password comes ONLY from DEV_ASSESSOR_EMAIL /
DEV_ASSESSOR_PASSWORD (server/app/config.py) -- if either is unset, no
password is set and that assessor simply cannot log in yet. There is no
hard-coded credential anywhere in this file.
"""
from sqlalchemy.orm import Session

from . import models
from .auth import hash_password
from .config import settings
from .db import SessionLocal
from .pack_import import REPO_ROOT, import_pack_cli
from .worker_tokens import generate_worker_token


def seed(db: Session) -> None:
    pack = import_pack_cli(REPO_ROOT / "packs" / "ae-con-q0602", db)

    assessor_email = settings.dev_assessor_email or "assessor.demo@parakh.test"
    assessor = db.query(models.User).filter_by(role="assessor", email=assessor_email).one_or_none()
    if assessor is None:
        assessor = models.User(role="assessor", display_name="Demo Assessor", email=assessor_email)
        db.add(assessor)
        db.flush()
    if settings.dev_assessor_password:
        assessor.password_hash = hash_password(settings.dev_assessor_password)

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
        _raw_token, token_hash = generate_worker_token()
        assessment = models.Assessment(
            worker_id=worker.id, pack_id=pack.id, status=status,
            assessor_id=assessor.id if status != "draft" else None,
            worker_token_hash=token_hash,
        )
        db.add(assessment)
        db.flush()
        for t in templates:
            db.add(models.AssessmentTask(assessment_id=assessment.id, task_code=t.task_code, budget_bytes=t.budget_bytes))

    db.commit()
    login_note = "password set from DEV_ASSESSOR_PASSWORD" if settings.dev_assessor_password else "NO password set (DEV_ASSESSOR_PASSWORD unset) -- cannot log in yet"
    print(f"seeded: pack={pack.qp_code} assessor={assessor.email} ({login_note}) workers={len(workers)}")


if __name__ == "__main__":
    session = SessionLocal()
    try:
        seed(session)
    finally:
        session.close()
