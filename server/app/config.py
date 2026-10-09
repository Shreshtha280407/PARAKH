from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PARAKH_")

    database_url: str = "postgresql+psycopg://parakh:parakh@localhost:5432/parakh"
    storage_root: Path = REPO_ROOT / "server" / "data" / "evidence"
    total_evidence_budget_bytes: int = 120 * 1024 * 1024


settings = Settings()
