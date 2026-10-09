"""P2 test fixtures. Deliberately separate from the P1 test suite
(tests/fixtures/ at the repo root, which tests packs/ae-con-q0602/ pack data
with tools/pack_validate.py + tools/audit_qp_traceability.py) -- this
directory tests the P2 FastAPI/SQLAlchemy backend instead.

Runs against an in-memory SQLite database per test, not PostgreSQL: there's
no Docker/Postgres available in this environment. The schema itself (same
SQLAlchemy models, same Alembic migration) was separately verified against
a real on-disk SQLite database via `alembic upgrade head` / `downgrade
base` -- see server/README.md for the real-Postgres path via
infra/docker-compose.yml, which this suite does not substitute for.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.app.db import Base, get_db
from server.app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def db_session():
    # StaticPool: the TestClient runs endpoints in a worker thread, which
    # would otherwise check out a *different* pooled connection -- and a
    # fresh sqlite ':memory:' connection is a brand-new, empty database.
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def pack_dir() -> Path:
    return REPO_ROOT / "packs" / "ae-con-q0602"


@pytest.fixture()
def imported_pack(db_session, pack_dir):
    from server.app.pack_import import import_pack

    return import_pack(db_session, pack_dir)


@pytest.fixture()
def worker(db_session):
    from server.app import models

    u = models.User(role="worker", display_name="Test Worker", phone="9999900001")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u
