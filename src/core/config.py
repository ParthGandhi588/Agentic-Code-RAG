"""Type-safe application configuration backed by Pydantic BaseSettings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # Application
    app_env: Literal["development", "production", "testing"] = Field(
        default="development", alias="APP_ENV"
    )
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # PostgreSQL & pgvector Database
    pg_host: str = Field(default="localhost", alias="PG_HOST")
    pg_port: int = Field(default=5432, alias="PG_PORT")
    pg_user: str = Field(default="agentic_user", alias="PG_USER")
    pg_password: str = Field(default="agentic_secure_pass", alias="PG_PASSWORD")
    pg_database: str = Field(default="agentic_code_rag_db", alias="PG_DATABASE")

    # LLM Providers
    llm_provider: Literal["gemini", "groq", "ollama"] = Field(
        default="gemini", alias="LLM_PROVIDER"
    )

    # Google Gemini
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    # Groq
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")

    # Ollama
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5-coder:7b", alias="OLLAMA_MODEL")

    # Embedding Settings
    embed_model: str = Field(default="BAAI/bge-small-en-v1.5", alias="EMBED_MODEL")
    embed_dim: int = Field(default=384, alias="EMBED_DIM")
    embed_batch_size: int = Field(default=128, alias="EMBED_BATCH_SIZE")

    # Ingestion Constraints & Security Limits
    max_file_size_bytes: int = Field(default=1_048_576, alias="MAX_FILE_SIZE_BYTES")  # 1 MB
    max_repo_files: int = Field(default=25_000, alias="MAX_REPO_FILES")
    temp_dir: str = Field(default="/tmp/agentic_code_rag", alias="TEMP_DIR")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def sync_database_url(self) -> str:
        """Standard sync PostgreSQL connection URL."""
        return f"postgresql://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_database}"

    @property
    def async_database_url(self) -> str:
        """Asyncpg-compatible PostgreSQL connection URL."""
        return f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_database}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns cached application settings instance."""
    return Settings()
