"""P2/P2.1 test fixtures. Deliberately separate from the P1 test suite
(tests/fixtures/ at the repo root, tested by tools/pack_validate.py and
tools/audit_qp_traceability.py -- no Python, no pytest, no server involved).

Backend selection: if TEST_DATABASE_URL is set, tests run against that
database (a real PostgreSQL instance, in CI and in `make test`-style local
runs against infra/docker-compose.yml's db service) -- this is REQUIRED for
test_jobs.py::test_concurrent_claims_never_double_process, which proves
`SELECT ... FOR UPDATE SKIP LOCKED` actually prevents two workers from
claiming the same job, something SQLite cannot demonstrate (it has no
row-level locking at all). If TEST_DATABASE_URL is unset, tests fall back
to a fast in-memory SQLite database -- fine for everything except that one
concurrency test, which fails loudly (not skipped) in that case so a bad
local run can't be mistaken for a passing one.
"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.app.db import Base, get_db
from server.app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _make_test_engine():
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL)
        # Postgres: start from a clean slate every test run.
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        return engine

    # StaticPool: TestClient runs endpoints in a worker thread, which would
    # otherwise check out a *different* pooled connection -- and a fresh
    # sqlite ':memory:' connection is a brand-new, empty database.
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def db_session():
    engine = _make_test_engine()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        if TEST_DATABASE_URL:
            Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(db_session, tmp_path):
    from server.app.routers import auth as auth_router
    from server.app.routers import uploads as uploads_router
    from server.app.storage import LocalDiskStorage

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # Isolate evidence storage per test -- the real server/data/evidence
    # directory is for actual dev/demo runs, never for tests, and reusing
    # it across test runs would let one test's leftover bytes corrupt
    # another's (assessment/session ids restart from 1 in each fresh
    # in-memory DB, so storage keys collide across test runs otherwise).
    original_storage = uploads_router._storage
    uploads_router._storage = LocalDiskStorage(tmp_path / "evidence")
    # The login throttle (server/app/routers/auth.py) is a module-level,
    # per-process dict keyed by email -- every test's `assessor` fixture
    # reuses the same literal email, so without clearing this a failed-login
    # test earlier in the suite would eventually lock out an unrelated
    # later test's legitimate login.
    auth_router._failed_login_attempts.clear()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        uploads_router._storage = original_storage
        auth_router._failed_login_attempts.clear()


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


@pytest.fixture()
def assessor(db_session):
    from server.app import models
    from server.app.auth import hash_password

    u = models.User(
        role="assessor", display_name="Test Assessor", email="assessor@test.local",
        password_hash=hash_password("correct horse battery staple"),
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture()
def assessor_token(assessor):
    from server.app.auth import create_access_token

    return create_access_token(assessor)


@pytest.fixture()
def assessor_headers(assessor_token):
    return {"Authorization": f"Bearer {assessor_token}"}


@pytest.fixture()
def admin(db_session):
    from server.app import models
    from server.app.auth import hash_password

    u = models.User(
        role="admin", display_name="Test Admin", email="admin@test.local",
        password_hash=hash_password("another strong passphrase"),
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture()
def admin_headers(admin):
    from server.app.auth import create_access_token

    token = create_access_token(admin)
    return {"Authorization": f"Bearer {token}"}


def create_assessment(client, worker, imported_pack):
    """Helper (not a fixture, needs per-test worker/pack combos): POST
    /assessments and return (assessment_json, worker_token)."""
    r = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id})
    assert r.status_code == 201, r.text
    body = r.json()
    return body, body["worker_token"]
