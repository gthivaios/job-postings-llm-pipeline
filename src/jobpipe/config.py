"""Typed settings loaded from environment / .env."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "jobpipe"
    db_password: str = ""
    raw_db: str = "raw_portals"
    analysis_db: str = "analysis"

    # LLM access
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_timeout_s: float = 120
    llm_max_retries: int = 3

    # Translation stage
    translate_model: str = "phi-4"  # alias from jobpipe.llm.MODELS or a full OpenRouter id
    translate_workers: int = 4
    chunk_max_words: int = 300
    chunk_max_chars: int = 2000
    unicode_form: Literal["NFC", "NFKC", "NFD", "NFKD"] = "NFKD"

    # Tracing: "opik" sends traces to Opik (cloud or self-hosted, see README); "none" disables it
    tracing: Literal["none", "opik"] = "none"

    def url(self, database: str) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{database}?charset=utf8mb4"
        )
