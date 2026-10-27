from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve paths relative to the pi/ directory
_PI_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ENV = _PI_ROOT / "config.env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_DEFAULT_ENV) if _DEFAULT_ENV.exists() else None,
        env_file_encoding="utf-8",
        env_prefix="SCOREBOARD_",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8080
    db_path: str = "data/scoreboard.db"
    team_policy: Literal["best", "replace"] = "best"

    push_url: str = ""
    push_token: str = ""
    push_status: str = "live"
    push_message: str = ""
    push_min_interval_seconds: float = 15.0

    def resolve_db_path(self) -> Path:
        path = Path(self.db_path)
        if not path.is_absolute():
            path = _PI_ROOT / path
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
