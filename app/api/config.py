"""API-specific configuration via Pydantic BaseSettings."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class APISettings(BaseSettings):
    """Settings specific to the API service."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://neochat:password@postgres:5432/neochat"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    rabbitmq_management_url: str = "http://guest:guest@rabbitmq:15672"

    # Zalo OA
    zalo_app_id: str = ""
    zalo_app_secret: str = ""
    zalo_webhook_secret: str = ""
    zalo_oa_id: str = ""
    zalo_callback_url: str = ""  # e.g., "https://your-domain.com" or "http://localhost:8000"
    zalo_code_verifier: str = ""  # PKCE code verifier, generate via: python -m app.api.scripts.generate_pkce

    # LLM
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # API-specific
    internal_api_key: str = "changeme"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    rate_limit_per_minute: int = 100

    # Worker settings (needed for prompt/queue interactions)
    context_window_size: int = 10
    max_tool_calls: int = 2
    llm_timeout_seconds: int = 15


api_settings = APISettings()


class AdminSettings(BaseSettings):
    """Settings specific to the admin control plane."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Session
    admin_session_ttl_seconds: int = 86400  # 24 hours
    admin_session_id_bytes: int = 32

    # Password
    admin_bcrypt_rounds: int = 12

    # Lockout
    admin_max_login_attempts: int = 5
    admin_lockout_minutes: int = 15

    # Rate limiting
    admin_login_rate_limit_per_minute: int = 10

    # CORS
    admin_cors_origins: str = "http://localhost:3000"


admin_settings = AdminSettings()
