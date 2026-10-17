#!/usr/bin/env python3
"""Isolated CI browser backend with in-memory test email transport.

Never imported by the product. Refuses cloud databases and any non-loopback
binding. Test records are created by browser tests through actual enrollment.
"""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.engine import make_url

url = make_url(os.environ["DATABASE_URL"])
if url.host not in ("localhost", "127.0.0.1") or url.database != "parakh_open_e2e" or os.environ.get("APP_ENV", "development") != "development":
    raise SystemExit("E2E server requires the isolated loopback parakh_open_e2e database")

from server.app.config import settings
from server.app.db import SessionLocal
from server.app.main import app
from server.app.pack_import import import_pack
from server.app.routers import reviewer
from fastapi import HTTPException

mailbox = {}
settings.reviewer_smtp_host = "test-transport.invalid"
settings.reviewer_email_from = "test@parakh.invalid"
settings.reviewer_allowed_emails = "reviewer@parakh.invalid"


def send_code(email, code, assessment_id, action):
    mailbox[(assessment_id, action)] = code


reviewer.send_code = send_code
with SessionLocal() as db:
    import_pack(db, Path(__file__).resolve().parents[1] / "packs/ae-con-q0602")


@app.get("/_test/code/{assessment_id}/{action}")
def code(assessment_id: int, action: str):
    if (assessment_id, action) not in mailbox:
        raise HTTPException(404)
    return {"code": mailbox[(assessment_id, action)]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18178)
