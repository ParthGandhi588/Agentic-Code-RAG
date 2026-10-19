"""Unit tests for application configuration."""

from src.core.config import Settings


def test_custom_settings() -> None:
    settings = Settings(
        APP_ENV="testing",
        PG_HOST="127.0.0.1",
        PG_PORT=5432,
        PG_USER="custom_user",
        PG_PASSWORD="custom_pass",
        PG_DATABASE="custom_db",
        LLM_PROVIDER="groq",
    )
    assert settings.app_env == "testing"
    assert settings.pg_host == "127.0.0.1"
    assert settings.llm_provider == "groq"
    assert (
        settings.sync_database_url
        == "postgresql://custom_user:custom_pass@127.0.0.1:5432/custom_db"
    )
    assert (
        settings.async_database_url
        == "postgresql+asyncpg://custom_user:custom_pass@127.0.0.1:5432/custom_db"
    )


def test_file_limits() -> None:
    settings = Settings()
    assert settings.max_file_size_bytes == 1_048_576
    assert settings.max_repo_files == 25_000
