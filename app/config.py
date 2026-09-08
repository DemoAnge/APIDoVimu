from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DoVimu API"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True

    api_key: str = ""

    download_dir: Path = ROOT_DIR / "storage" / "downloads"
    max_concurrent_downloads: int = 2
    job_ttl_seconds: int = 3600
    max_duration_seconds: int = 14400
    max_file_bytes: int = 2 * 1024 * 1024 * 1024
    socket_timeout: int = 30

    ffmpeg_location: str = ""
    cookies_file: str = ""
    proxy: str = ""

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    return settings
