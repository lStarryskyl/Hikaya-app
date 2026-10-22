"""Settings read from the environment. Keys never live in code."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"
    database_url: str = "postgresql+asyncpg://hikaya:hikaya@localhost:5432/hikaya"
    media_dir: str = "./data/media"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    jwt_secret: str = "change-me-in-env"

    # Worker behaviour
    worker_poll_seconds: float = 1.0
    job_stale_after_seconds: int = 600

    # Provider choices. Each step can be switched without code changes.
    stt_provider: str = "elevenlabs"
    tts_provider: str = "elevenlabs"
    llm_provider: str = "azure"
    video_provider: str = "fal"

    # Safety switches
    live_ai_enabled: bool = False
    enable_ai_video: bool = False
    spend_cap_usd_total: float = 25.0
    spend_cap_usd_daily: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
