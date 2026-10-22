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

    # Sign-in. The cookie is only marked Secure when the site is served over HTTPS.
    cookie_secure: bool = False
    session_ttl_days: int = 7

    # Staff accounts, created at start-up when both email and password are set.
    seed_admin_email: str = ""
    seed_admin_password: str = ""
    seed_reviewer_email: str = ""
    seed_reviewer_password: str = ""

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
