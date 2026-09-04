"""SkillRadar v0.5.3 application settings. Secrets never logged."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SkillRadar"
    app_version: str = "0.5.3"
    secret_key: str = Field(default="dev-only-change-me-please-use-32bytes")
    jwt_expire_minutes: int = 10080
    database_url: str = "sqlite:///./data/skillradar.db"
    redis_url: str = ""
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    qdrant_url: str = ""
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "skillradar"
    minio_secure: bool = False
    object_dir: str = ""
    vector_store_path: str = ""
    github_tokens: str = ""
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"
    clone_dir: str = "./data/clones"
    encryption_key: str = ""
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    rate_limit_per_minute: int = 60
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True

    def token_list(self) -> list[str]:
        return [t.strip() for t in self.github_tokens.split(",") if t.strip()]

    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    def data_dir(self) -> Path:
        url = self.database_url
        if url.startswith("sqlite") and ":memory:" not in url and url not in {"sqlite://", "sqlite:///:memory:"}:
            path = url.split("///")[-1]
            parent = Path(path).parent
            if str(parent) not in {".", ""}:
                parent.mkdir(parents=True, exist_ok=True)
        Path(self.clone_dir).mkdir(parents=True, exist_ok=True)
        root = object_dir_path(self)
        root.mkdir(parents=True, exist_ok=True)
        return Path(self.clone_dir)


def object_dir_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    custom = (settings.object_dir or "").strip()
    if custom:
        return Path(custom)
    return Path(settings.clone_dir).resolve().parent / "objects"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    get_settings.cache_clear()
    os.environ.setdefault("APP_VERSION", "0.5.3")
