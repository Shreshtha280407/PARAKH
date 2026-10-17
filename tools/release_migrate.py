#!/usr/bin/env python3
"""Locked, version-aware expand migrations. Never prints connection strings.

Only this release step migrates the cloud database; API/worker startup never
does. Old application versions must work with the expanded schema on failure.
"""
import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def migrate(url: str, expected_branch: str, output: Path | None = None):
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or "-pooler" in (parsed.host or ""):
        raise ValueError("migrations require a direct PostgreSQL connection")
    if expected_branch and not os.environ.get("PARAKH_LOCAL_MIGRATION_TEST"):
        # Neon hostname is ep-*, not br-*; compare against a reviewed endpoint
        # hostname from hosting-target.json rather than guessing a branch from DNS.
        if parsed.host != expected_branch:
            raise ValueError("migration database does not match the reviewed deployment endpoint")
    os.environ["PARAKH_MIGRATION_ONLY"] = "1"
    os.environ["NEON_DIRECT_DATABASE_URL"] = url
    cfg = Config(str(Path(__file__).resolve().parents[1] / "server/alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "server/alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as connection:
        connection.execute(text("SET lock_timeout = '60s'"))
        connection.execute(text("SELECT pg_advisory_lock(72026019)"))
        connection.commit()
        try:
            before = MigrationContext.configure(connection).get_current_revision()
            connection.commit()
            if before != head:
                cfg.attributes["connection"] = connection
                command.upgrade(cfg, "head")
                connection.commit()
            after = MigrationContext.configure(connection).get_current_revision()
            connection.commit()
            if after != head:
                raise RuntimeError("migration did not reach the expected head")
            result = {"before": before, "after": after, "changed": before != after}
            if output:
                output.write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result))
            return result
        finally:
            connection.rollback()
            connection.execute(text("SELECT pg_advisory_unlock(72026019)"))
            connection.commit()
    engine.dispose()


if __name__ == "__main__":
    target = json.loads((Path(__file__).resolve().parents[1] / "infra/hosting-target.json").read_text())
    try:
        migrate(os.environ["NEON_DIRECT_DATABASE_URL"], target["neon_direct_host"], Path("migration-result.json"))
    except Exception as error:
        # SQLAlchemy exceptions can contain URLs/SQL parameters; never dump them.
        print(f"Migration failed ({type(error).__name__}); deployment must stop. No downgrade attempted.")
        raise SystemExit(1)
