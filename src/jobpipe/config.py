"""Typed settings loaded from environment / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "jobpipe"
    db_password: str = ""
    raw_db: str = "raw_portals"
    analysis_db: str = "analysis"

    def url(self, database: str) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{database}?charset=utf8mb4"
        )
