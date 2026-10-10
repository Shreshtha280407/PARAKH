import secrets
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    # "development" | "staging" | "production" -- gates the fail-fast
    # checks below (and CORS defaults, see main.py).
    app_env: str = "development"

    database_url: str = "postgresql+psycopg://parakh:parakh@localhost:5432/parakh"
    evidence_dir: Path = REPO_ROOT / "server" / "data" / "evidence"

    # Ed25519 tamper-evident report signing (server/app/report_signing.py).
    # Hex-encoded 32-byte seed. Auto-generated in development if unset (a
    # fresh key each process restart is fine for a local demo -- reports
    # signed by a previous run simply won't verify, which is acceptable
    # outside a real deployment). staging/production MUST set it
    # explicitly, enforced below.
    report_signing_private_key: str | None = None
    report_signing_key_id: str = "dev-key-1"

    @model_validator(mode="after")
    def _report_signing_key_fail_fast(self) -> "Settings":
        if self.report_signing_private_key is None:
            if self.app_env != "development":
                raise ValueError(
                    "REPORT_SIGNING_PRIVATE_KEY must be set outside development "
                    f"(APP_ENV='{self.app_env}') -- refusing to start with no report signing key."
                )
            self.report_signing_private_key = secrets.token_bytes(32).hex()
        return self

    # JWT (assessor/admin auth only -- workers never log in, see server/app/auth.py)
    jwt_secret: str | None = None  # dev-only random fallback generated below; MUST be set outside development
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "kaushalpramaan"
    jwt_audience: str = "kaushalpramaan-dashboard"
    jwt_expire_minutes: int = 60

    @model_validator(mode="after")
    def _jwt_secret_fail_fast(self) -> "Settings":
        if self.jwt_secret is None:
            if self.app_env != "development":
                raise ValueError(
                    f"JWT_SECRET must be set outside development (APP_ENV='{self.app_env}') -- "
                    "a random per-process fallback would invalidate every token on restart and "
                    "differ across replicas."
                )
            self.jwt_secret = secrets.token_urlsafe(32)
        return self

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
    # Crash recovery (P2.2 section 9): a job claimed but still "running"
    # past this long is presumed to belong to a worker that crashed/was
    # killed mid-job -- see jobs.recover_stale_jobs. Generous enough for a
    # real evidence-verify/thumbnail job, short enough to recover promptly.
    job_lease_seconds: int = 300

    # CORS: the dashboard (Vite dev server / its own Docker container) is a
    # different origin (port) than the API. The dashboard now authenticates
    # via cookies (P2.2 section 7), which requires allow_credentials=True
    # (see main.py) -- and browsers flatly reject a wildcard origin
    # combined with credentials, so "*" is never valid here (enforced
    # below), regardless of APP_ENV.
    cors_allow_origins: str = "http://localhost:5173"

    @model_validator(mode="after")
    def _cors_origins_fail_fast(self) -> "Settings":
        origins = [o.strip() for o in self.cors_allow_origins.split(",")]
        if "*" in origins:
            raise ValueError(
                "CORS_ALLOW_ORIGINS must not be '*' -- cookie-based dashboard sessions require "
                "allow_credentials=True, and browsers reject a wildcard origin combined with "
                "credentials. Set it to the real dashboard origin(s) instead (comma-separated)."
            )
        if self.app_env != "development" and any(
            o.startswith("http://localhost") or o.startswith("http://127.0.0.1") for o in origins
        ):
            raise ValueError(
                f"CORS_ALLOW_ORIGINS contains a localhost origin outside development (APP_ENV='{self.app_env}') "
                "-- set it to the real deployed dashboard origin(s)."
            )
        return self


settings = Settings()
