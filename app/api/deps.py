from fastapi import Header, HTTPException, Request

from app.config import Settings
from app.services.downloader import DownloadRunner
from app.services.extractor import MediaExtractor
from app.services.jobs import JobStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_jobs(request: Request) -> JobStore:
    return request.app.state.jobs


def get_extractor(request: Request) -> MediaExtractor:
    return request.app.state.extractor


def get_runner(request: Request) -> DownloadRunner:
    return request.app.state.runner


def ffmpeg_available(request: Request) -> bool:
    return bool(request.app.state.ffmpeg_available)


async def verify_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    expected = request.app.state.settings.api_key
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida.")
