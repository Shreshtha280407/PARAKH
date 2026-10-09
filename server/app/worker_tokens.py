"""Opaque, assessment-scoped capability tokens for worker-side requests.

Product decision: the worker mobile app has no conventional login/signup.
P2.1 still needs *some* way to stop one device from reading/writing another
worker's assessment just by guessing a small integer id -- so instead of a
worker account, each assessment gets one random, unguessable, bearer-style
capability token at creation time:

  - POST /assessments returns the raw token exactly once, in the response
    body. The server never stores or logs the raw value again.
  - Only its SHA-256 hash is persisted (assessments.worker_token_hash),
    the same pattern used for API keys -- a DB leak doesn't hand out usable
    tokens.
  - Every worker-facing mutation (evidence metadata, upload sessions, chunk
    upload, complete) requires this token, via the `X-Worker-Token` header,
    matching the specific assessment it's scoped to.

Boundaries (temporary P2 approach, revisit before pilot):
  - There is no token rotation, revocation list, or expiry -- a token is
    valid for the assessment's lifetime. Losing a phone mid-assessment means
    losing the ability to resume it (no recovery flow exists yet).
  - The token is not tied to a device identity, just "whoever has it can
    act as this assessment's worker" -- equivalent to a bearer capability,
    not proof of who the worker is. Real worker identity/liveness is a
    product decision for a later phase, not solved here.
  - GET /assessments/{id} accepts EITHER this token OR an assessor/admin
    JWT, since both workers (checking their own progress) and assessors
    (reviewing) need to read assessment detail.
"""
import hashlib
import secrets

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .db import get_db


def generate_worker_token() -> tuple[str, str]:
    """Returns (raw_token, sha256_hex_hash). Only the hash is ever stored."""
    raw = secrets.token_urlsafe(settings.worker_token_bytes)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def hash_worker_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def require_worker_token_for_assessment(assessment_id: int):
    """FastAPI dependency: the X-Worker-Token header must match the given
    assessment's stored hash. 401 if missing/wrong, 404 if the assessment
    doesn't exist (don't leak existence to a bad token)."""

    def _check(
        x_worker_token: str | None = Header(default=None),
        db: Session = Depends(get_db),
    ) -> models.Assessment:
        assessment = db.get(models.Assessment, assessment_id)
        if assessment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
        if not x_worker_token or hash_worker_token(x_worker_token) != assessment.worker_token_hash:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid X-Worker-Token for this assessment")
        return assessment

    return _check
