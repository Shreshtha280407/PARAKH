"""Apply the real migration chain in an isolated PostgreSQL schema."""
import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_expand_migration_preserves_historical_records_and_is_idempotent(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("migration verification requires TEST_DATABASE_URL (PostgreSQL)")
    schema = "open_migration_" + uuid.uuid4().hex
    engine = create_engine(url)
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "server/alembic.ini"))
    cfg.set_main_option("script_location", str(root / "server/alembic"))
    monkeypatch.setenv("PARAKH_MIGRATION_ONLY", "1")
    monkeypatch.setenv("NEON_DIRECT_DATABASE_URL", url)
    with engine.connect() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
        db.execute(text(f'SET search_path TO "{schema}"'))
        db.commit()
        cfg.attributes["connection"] = db
        try:
            command.upgrade(cfg, "b89e72c4d010")
            db.execute(text("INSERT INTO users (id, role, display_name, created_at) VALUES (1, 'worker', 'Historical Person', now())"))
            db.execute(text("INSERT INTO qualification_packs (id, qp_code, qp_version, pack_version, qp_name, source_pdf_sha256, source_pdf_path, minimum_aggregate_passing_percent, final_evidence_budget_bytes, imported_at) VALUES (1, 'QP', '1', '1', 'Pack', :hash, 'private', 70, 100, now())"), {"hash": "a" * 64})
            db.execute(text("INSERT INTO assessments (id, worker_id, pack_id, status, total_bytes_used, worker_token_hash, worker_token_status, revision_number, created_at) VALUES (1, 1, 1, 'submitted', 0, :hash, 'active', 1, now())"), {"hash": "b" * 64})
            db.commit()
            command.upgrade(cfg, "head")
            db.commit()
            row = db.execute(text("SELECT provenance, public_name_consent FROM assessments WHERE id=1")).one()
            assert row == ("legacy", False)
            assert db.execute(text("SELECT display_name FROM users WHERE id=1")).scalar() == "Historical Person"
            assert "reviewer_sessions" in inspect(db).get_table_names(schema=schema)
            assert inspect(db).get_columns("signed_reports", schema=schema)[-1]["name"] == "reviewer_identity"
            command.upgrade(cfg, "head")
            db.commit()
            assert db.execute(text("SELECT count(*) FROM assessments")).scalar() == 1
            # The actual release runner must skip upgrade entirely at head.
            from tools.release_migrate import migrate
            from sqlalchemy.engine import make_url
            scoped_url = make_url(url).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
            with monkeypatch.context() as context:
                context.setattr(command, "upgrade", lambda *args: pytest.fail("unchanged schema must not run DDL"))
                assert migrate(scoped_url, "")["changed"] is False
        finally:
            db.rollback()
            db.execute(text("SET search_path TO public"))
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            db.commit()
    engine.dispose()
