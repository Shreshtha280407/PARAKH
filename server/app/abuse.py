"""Shared database limits survive process restarts and multiple API replicas.

Never trust caller-supplied X-Forwarded-For. Configure uvicorn's trusted proxy
addresses at the platform boundary before using forwarded client addresses.
The global ceilings also bound damage when address attribution is unavailable.
"""
import datetime
import hashlib

from fastapi import HTTPException, Request
from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from . import models
from .config import settings


def throttle(db: Session, key: str, limit: int, seconds: int = 3600) -> None:
    now = models.utcnow()
    digest = hashlib.sha256(key.encode()).hexdigest()
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    table = models.AbuseCounter
    expired = table.resets_at <= now
    statement = insert(table).values(key=digest, count=1, resets_at=now + datetime.timedelta(seconds=seconds))
    statement = statement.on_conflict_do_update(
        index_elements=[table.key],
        set_={"count": case((expired, 1), else_=table.count + 1),
              "resets_at": case((expired, now + datetime.timedelta(seconds=seconds)), else_=table.resets_at)},
    ).returning(table.count)
    count = db.execute(statement).scalar_one()
    db.commit()  # Denied attempts must count too. Call BEFORE business mutations.
    if count > limit:
        raise HTTPException(429, "request limit reached; try later", headers={"Retry-After": str(seconds)})


def source(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enrollment_limits(db: Session, request: Request) -> None:
    throttle(db, "enroll-global", 100, 86400)
    throttle(db, "enroll-ip:" + source(request), 20)


def enrollment_capacity(db: Session) -> None:
    if db.query(models.Assessment).count() >= settings.public_enrollment_max_assessments:
        raise HTTPException(503, "enrollment capacity reached; contact the operator")
