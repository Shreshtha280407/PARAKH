import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    database_url: str = "postgresql+psycopg://parakh:parakh@localhost:5432/parakh"
    evidence_dir: Path = REPO_ROOT / "server" / "data" / "evidence"

    # JWT (assessor/admin auth only -- workers never log in, see server/app/auth.py)
    jwt_secret: str = secrets.token_urlsafe(32)  # dev-only fallback; MUST be set via env in any real deployment
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "kaushalpramaan"
    jwt_audience: str = "kaushalpramaan-dashboard"
    jwt_expire_minutes: int = 60

    # Opaque worker-assessment capability tokens (see docs/worker_capability_tokens.md)
    worker_token_bytes: int = 32

    # Dev-only assessor bootstrap (server/app/seed.py). Never defaulted to a
    # real credential -- if unset, seeding a dev assessor is simply skipped.
    dev_assessor_email: str | None = None
    dev_assessor_password: str | None = None

    # Resumable upload sessions
    upload_session_ttl_minutes: int = 120
    upload_chunk_max_bytes: int = 2 * 1024 * 1024  # 2 MiB/chunk ceiling

    # Background worker
    job_poll_interval_seconds: float = 2.0
    job_max_attempts: int = 3

    # CORS: the dashboard (Vite dev server / its own Docker container) is a
    # different origin than the API. "*" is fine for this local demo stack
    # (no cookies, no credentialed requests -- auth is a Bearer header);
    # tighten to the real dashboard origin(s) before any non-demo exposure.
    cors_allow_origins: str = "*"


settings = Settings()
