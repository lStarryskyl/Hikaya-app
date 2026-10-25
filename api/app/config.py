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

    # Load the seven demo stories, places and photos at start-up (python -m app.seed_demo).
    seed_demo_data: bool = True

    # Staff accounts, created at start-up when both email and password are set.
    seed_admin_email: str = ""
    seed_admin_password: str = ""
    seed_reviewer_email: str = ""
    seed_reviewer_password: str = ""

    # Uploads
    max_audio_upload_mb: float = 100
    max_audio_minutes: float = 60
    max_photo_upload_mb: float = 15
    max_photos_per_story: int = 12
    # Refused before decoding, so a small file cannot expand into a huge image in memory.
    max_photo_megapixels: float = 40

    # Worker behaviour
    worker_poll_seconds: float = 1.0
    job_stale_after_seconds: int = 600

    # Provider choices. Each step can be switched without code changes. The defaults are the
    # fakes, so nothing is called or paid for until the keys are in .env and the provider is
    # chosen here; see docs/DECISIONS.md for the intended real choices.
    stt_provider: str = "fake"
    tts_provider: str = "fake"
    llm_provider: str = "fake"
    video_provider: str = "fal"
    fal_key: str = ""
    higgsfield_key_id: str = ""
    higgsfield_key_secret: str = ""
    higgsfield_media_hosts: list[str] = Field(
        default_factory=lambda: [
            "higgsfield.ai",
            "amazonaws.com",
            "cloudfront.net",
            "storage.googleapis.com",
        ]
    )
    google_cloud_project: str = Field("", pattern=r"^$|^[a-z][a-z0-9-]{4,62}[a-z0-9]$")
    google_cloud_location: str = Field("us-central1", pattern=r"^[a-z0-9-]+$")
    google_access_token: str = ""
    custom_video_endpoint: str = ""
    custom_video_token: str = ""
    custom_video_estimate_usd: float = Field(0.0, ge=0)
    video_estimate_usd: float = Field(1.0, ge=0)
    video_poll_seconds: float = Field(3.0, ge=0.1, le=30)
    # Azure OpenAI (#12): polishing, translation and moderation. The deployment is the name
    # given to the model in Azure AI Foundry. Prices are per million tokens for that model
    # (defaults: gpt-5.4-mini, Global Standard, docs/research/speech-voice-and-llm.md).
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    azure_openai_input_usd_per_million: float = Field(0.75, ge=0)
    azure_openai_output_usd_per_million: float = Field(4.5, ge=0)
    # For reasoning models only (minimal | low | medium | high); empty sends nothing.
    azure_openai_reasoning_effort: str = Field("", pattern=r"^$|^(none|minimal|low|medium|high)$")
    # Transcription (#13). ElevenLabs Scribe is billed to the card; Azure fast transcription
    # to the Azure budget. Endpoint: https://<resource>.cognitiveservices.azure.com, or leave
    # it empty to use the regional host. Prices per audio hour.
    elevenlabs_stt_model: str = "scribe_v2"
    elevenlabs_stt_usd_per_hour: float = Field(0.22, ge=0)
    azure_speech_key: str = ""
    azure_speech_region: str = Field("", pattern=r"^$|^[a-z0-9]+$")
    azure_speech_endpoint: str = ""
    azure_speech_arabic_locale: str = "ar-JO"
    azure_stt_usd_per_hour: float = Field(0.36, ge=0)
    voice_clone_provider: str = "fake"
    elevenlabs_api_key: str = ""
    # Conservative reservation, configurable for the account's plan.
    voice_clone_estimate_usd: float = Field(1.0, ge=0)

    dummy_checkout_seconds: float = Field(1.5, ge=0, le=10)

    # Safety switches
    live_ai_enabled: bool = False
    enable_ai_video: bool = False
    spend_cap_usd_total: float = 25.0
    spend_cap_usd_daily: float = 10.0
    # Azure is paid from its own budget, so it has its own cap.
    spend_cap_usd_azure: float = 50.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
