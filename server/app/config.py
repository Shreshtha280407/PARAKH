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
    # Hex-encoded 32-byte seed. P7: REQUIRED in every environment, including
    # development -- a signing key that regenerates itself every process
    # restart would silently invalidate every previously-signed report
    # (and, worse, would mean the "same" dev key_id resolves to a different
    # actual key across runs). Generate one once with:
    #   python -c "import secrets; print(secrets.token_bytes(32).hex())"
    # and set it in .env -- never commit the real value to git.
    report_signing_private_key: str | None = None
    report_signing_key_id: str = "dev-key-1"
    # Base URL the signed PDF's QR code points at (the dashboard's own
    # public, unauthenticated #/verify/:reportId page -- see
    # apps/dashboard/src/pages/VerifyReportPage.tsx), e.g.
    # "http://localhost:5173" locally or the real deployed dashboard origin.
    # Deliberately separate from cors_allow_origins: that gates which
    # origins may call the API with credentials; this is just where a QR
    # scan should navigate a browser, which may legitimately differ (e.g. a
    # LAN IP a phone's camera app can actually reach, vs the dashboard's own
    # browser origin).
    report_verify_base_url: str = "http://localhost:5173"
    # Retired keys, so a report signed before a key rotation stays
    # verifiable: "key_id1:hex_public_key1,key_id2:hex_public_key2". Only
    # public keys ever live here -- a retired private key is not needed to
    # verify, only to sign, and is never kept once retired.
    report_signing_key_history: str = ""

    @model_validator(mode="after")
    def _report_signing_key_fail_fast(self) -> "Settings":
        if self.report_signing_private_key is None:
            raise ValueError(
                "REPORT_SIGNING_PRIVATE_KEY must be set (including in development) -- a "
                "regenerate-on-every-restart fallback would silently invalidate every "
                "previously-signed report. Generate one once with: "
                "python -c \"import secrets; print(secrets.token_bytes(32).hex())\" "
                "and set it in .env."
            )
        return self

    def report_signing_key_history_map(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for pair in self.report_signing_key_history.split(","):
            pair = pair.strip()
            if not pair:
                continue
            key_id, _, pubkey = pair.partition(":")
            if key_id and pubkey:
                result[key_id] = pubkey
        return result

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

    # --- evidence storage backend (server/app/storage.py) ---
    # "local" (default) keeps the existing private-Docker-volume
    # LocalDiskStorage used by infra/docker-compose.yml, the offline/LAN
    # deployment and every existing test -- unchanged, and requiring no
    # cloud credential whatsoever. "s3" selects the S3-compatible backend
    # (Neon Object Storage, MinIO, or any S3 API) for a hosted deployment
    # where the API and worker run on ephemeral filesystems and cannot
    # share a volume.
    storage_backend: str = "local"
    # S3-compatible endpoint, e.g. Neon Object Storage's bucket endpoint.
    # Required when storage_backend == "s3"; ignored otherwise.
    s3_endpoint_url: str | None = None
    s3_region: str = "auto"
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    @model_validator(mode="after")
    def _storage_backend_fail_fast(self) -> "Settings":
        if self.storage_backend not in ("local", "s3"):
            raise ValueError(
                f"STORAGE_BACKEND must be 'local' or 's3', got {self.storage_backend!r}."
            )
        if self.storage_backend == "s3":
            missing = [
                name for name, value in (
                    ("S3_ENDPOINT_URL", self.s3_endpoint_url),
                    ("S3_BUCKET", self.s3_bucket),
                    ("S3_ACCESS_KEY_ID", self.s3_access_key_id),
                    ("S3_SECRET_ACCESS_KEY", self.s3_secret_access_key),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "STORAGE_BACKEND='s3' requires " + ", ".join(missing) + " -- a hosted "
                    "deployment must never silently fall back to a local disk the worker "
                    "and API do not share."
                )
        return self

    # Optional cookie Domain attribute (P10 hosted-deployment readiness).
    # None (the default) makes the session/CSRF cookies host-only, which is
    # correct and sufficient when the dashboard and API are served from the
    # exact same origin (e.g. one reverse proxy forwarding both). Only set
    # this if the dashboard and API are deployed on different subdomains of
    # the same parent domain (e.g. dashboard.example.org + api.example.org),
    # in which case it should be the shared parent (".example.org"). Never
    # set it to a bare localhost/IP host in development -- browsers reject
    # a Domain attribute on cookies for those.
    cookie_domain: str | None = None

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
