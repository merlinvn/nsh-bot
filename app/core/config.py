"""Shared settings loaded from environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Shared settings for all services."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://neochat:password@postgres:5432/neochat"
    postgres_db: str = "neochat"
    postgres_user: str = "neochat"
    postgres_password: str = "changeme"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"

    # Zalo OA
    zalo_app_id: str = ""
    zalo_app_secret: str = ""
    zalo_access_token: str = ""
    zalo_refresh_token: str = ""
    zalo_webhook_secret: str = ""
    zalo_oa_id: str = ""

    # LLM Provider: "anthropic" or "openai-compat"
    llm_provider: str = "anthropic"

    # Anthropic (if llm_provider = "anthropic")
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # OpenAI-Compatible (if llm_provider = "openai-compat")
    # Works with Ollama, LM Studio, LocalAI, Azure OpenAI, etc.
    openai_base_url: str = "http://localhost:11434/v1"
    openai_api_key: str = "ollama"  # Often not needed for local
    openai_model: str = "llama3.2"

    # API
    internal_api_key: str = "changeme"
    cors_origins: str = "*"
    log_level: str = "INFO"
    rate_limit_per_minute: int = 100

    # Worker
    worker_metrics_port: int = 8080
    context_window_size: int = 10
    max_tool_calls: int = 2
    llm_timeout_seconds: int = 15

    # Dev mode: restrict processing to a single Zalo user ID
    # Leave empty to process all users normally
    dev_zalo_user_id: str = ""

    # MCP Server URL(s) — comma-separated list of MCP server URLs.
    # MCPClient tries each URL in order and uses the first successful one.
    # Example: http://nsh-mcp:8080,http://backup-mcp:8080
    mcp_server_urls: str = "http://nsh-mcp:8080"


_settings_instance: Settings | None = None


def get_settings() -> Settings:
    """Get or create the singleton settings instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


settings = get_settings()
