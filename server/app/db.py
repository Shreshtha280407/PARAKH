from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str | None = None):
    url = database_url or settings.database_url
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})

    # Managed/serverless PostgreSQL (Neon) differs from the local Docker
    # Compose `db` service in two ways that matter here:
    #
    #  * it scales to zero and closes idle connections, so a pooled
    #    connection can be dead by the time it is checked out again --
    #    pool_pre_ping spends one cheap round-trip to find out and
    #    transparently replaces it, instead of surfacing a random
    #    OperationalError on the next real query (and pool_recycle retires
    #    connections before an upstream idle timeout can do it first);
    #  * its connection allowance is far smaller than a self-hosted
    #    Postgres, and PARAKH runs an API *and* a worker against the same
    #    database -- so the pool is bounded deliberately rather than left
    #    at SQLAlchemy's default, which each process would otherwise grow
    #    to 5 + 10 overflow.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=5,
        pool_timeout=30,
    )


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
