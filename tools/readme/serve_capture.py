#!/usr/bin/env python3
"""Run the real API against a disposable local README-capture database.

No cloud credentials, production records, or mocked API responses are used.
Run from the repository root with server/.venv/bin/python.
"""
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
STATE = Path('/tmp/parakh-readme-capture')
STATE.mkdir(exist_ok=True)
key = STATE / 'signing-key'
if not key.exists():
    key.write_text(secrets.token_hex(32))
    key.chmod(0o600)
os.environ.update(
    APP_ENV='development',
    DATABASE_URL=f'sqlite:///{STATE}/capture.sqlite3',
    EVIDENCE_DIR=str(STATE / 'evidence'),
    STORAGE_BACKEND='local',
    REPORT_SIGNING_PRIVATE_KEY=key.read_text().strip(),
    REPORT_SIGNING_KEY_ID='readme-local-only',
    REPORT_VERIFY_BASE_URL='http://127.0.0.1:18197',
    CORS_ALLOW_ORIGINS='http://127.0.0.1:18197',
)
sys.path.insert(0, str(ROOT))
from server.app import models  # noqa: E402,F401
from server.app.db import Base, engine, SessionLocal  # noqa: E402
from server.app.pack_import import import_pack  # noqa: E402
from server.app.main import app  # noqa: E402
import uvicorn  # noqa: E402

Base.metadata.create_all(engine)
with SessionLocal() as db:
    import_pack(db, ROOT / 'packs/ae-con-q0602')
print('README capture API: isolated SQLite and private local media, port 18198', flush=True)
uvicorn.run(app, host='127.0.0.1', port=18198)
