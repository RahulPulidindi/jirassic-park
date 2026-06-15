"""Runtime configuration."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JP_", env_file=".env", extra="ignore")

    data_dir: str = os.environ.get("DATA_DIR", "/data")
    static_dir: str = os.environ.get("STATIC_DIR", "/app/static")
    port: int = int(os.environ.get("PORT", "8080"))

    secret_key: str = os.environ.get(
        "JP_SECRET_KEY", "jurassic-park-secret-not-for-prod"
    )

    admin_token: str = os.environ.get("JP_ADMIN_TOKEN", "admin-token-jurassic")

    log_level: str = "info"

    @property
    def state_db_path(self) -> Path:
        return Path(self.data_dir) / "state.db"

    @property
    def seed_db_path(self) -> Path:
        return Path(self.data_dir) / "seed.db"

    @property
    def state_db_url(self) -> str:
        return f"sqlite:///{self.state_db_path}"


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings()
