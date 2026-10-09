"""Shared budget/quota math: per-task budget (tasks.json) and the 120 MB
total (qp pack final_evidence_budget_bytes). Used by both the evidence
metadata endpoint and the upload-session endpoint so the same rule applies
everywhere bytes get counted, not just at upload time.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models


def task_bytes_committed(db: Session, assessment_task_id: int) -> int:
    """Evidence already recorded + bytes claimed by still-open upload sessions."""
    evidence = db.query(func.coalesce(func.sum(models.EvidenceItem.declared_size_bytes), 0)).filter(
        models.EvidenceItem.assessment_task_id == assessment_task_id
    ).scalar()
    open_sessions = db.query(func.coalesce(func.sum(models.UploadSession.claimed_size_bytes), 0)).filter(
        models.UploadSession.assessment_task_id == assessment_task_id,
        models.UploadSession.status == "open",
    ).scalar()
    return int(evidence) + int(open_sessions)


def assessment_bytes_committed(db: Session, assessment_id: int) -> int:
    task_ids = [row.id for row in db.query(models.AssessmentTask.id).filter(
        models.AssessmentTask.assessment_id == assessment_id
    )]
    return sum(task_bytes_committed(db, tid) for tid in task_ids)


class QuotaExceeded(Exception):
    def __init__(self, message: str, task_remaining: int, total_remaining: int):
        super().__init__(message)
        self.task_remaining = task_remaining
        self.total_remaining = total_remaining


def check_quota(db: Session, assessment_task: models.AssessmentTask, requested_bytes: int, total_budget_bytes: int) -> None:
    task_remaining = assessment_task.budget_bytes - task_bytes_committed(db, assessment_task.id)
    total_remaining = total_budget_bytes - assessment_bytes_committed(db, assessment_task.assessment_id)
    if requested_bytes > task_remaining:
        raise QuotaExceeded(
            f"{requested_bytes} bytes exceeds task {assessment_task.task_code}'s remaining budget of {task_remaining} bytes",
            task_remaining, total_remaining,
        )
    if requested_bytes > total_remaining:
        raise QuotaExceeded(
            f"{requested_bytes} bytes exceeds the assessment's remaining 120 MB total quota of {total_remaining} bytes",
            task_remaining, total_remaining,
        )
