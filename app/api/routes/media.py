import asyncio

from fastapi import APIRouter, Depends

from app.api.deps import (
    ffmpeg_available,
    get_extractor,
    get_jobs,
    get_runner,
    get_settings,
    verify_api_key,
)
from app.config import Settings
from app.core.exceptions import MediaTooLargeError, QualityNotAvailableError, UnsupportedMediaError
from app.core.urls import validate_media_url
from app.models.schemas import (
    DownloadRequest,
    InspectRequest,
    InspectResponse,
    JobCreatedResponse,
    JobStatus,
)
from app.services.downloader import DownloadRunner
from app.services.extractor import MediaExtractor
from app.services.jobs import JobStore
from app.services.normalize import normalize_media
from app.services.quality import parse_quality_id

router = APIRouter(
    prefix="/api/v1/media",
    tags=["media"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/inspect", response_model=InspectResponse)
async def inspect_media(
    payload: InspectRequest,
    extractor: MediaExtractor = Depends(get_extractor),
    ffmpeg: bool = Depends(ffmpeg_available),
) -> InspectResponse:
    url = validate_media_url(payload.url)
    info = await asyncio.to_thread(extractor.inspect, url, payload.playlist)
    result = normalize_media(info, ffmpeg)
    if not result.is_playlist and not result.video and not result.audio:
        raise UnsupportedMediaError(
            "No hay formatos descargables para este enlace. "
            "Si es un video en alta calidad, instala FFmpeg para unir audio y video."
        )
    return result


@router.post("/download", response_model=JobCreatedResponse, status_code=202)
async def start_download(
    payload: DownloadRequest,
    extractor: MediaExtractor = Depends(get_extractor),
    jobs: JobStore = Depends(get_jobs),
    runner: DownloadRunner = Depends(get_runner),
    ffmpeg: bool = Depends(ffmpeg_available),
    settings: Settings = Depends(get_settings),
) -> JobCreatedResponse:
    url = validate_media_url(payload.url)
    parse_quality_id(payload.quality_id)
    info = await asyncio.to_thread(extractor.inspect, url, False)
    result = normalize_media(info, ffmpeg)
    if result.duration and result.duration > settings.max_duration_seconds:
        raise MediaTooLargeError("El video es demasiado largo para descargarlo.")

    known_ids = {item.id for item in result.video + result.audio}
    if known_ids and payload.quality_id not in known_ids:
        raise QualityNotAvailableError("Esa calidad no está disponible para este enlace.")

    job = jobs.create(url=url, quality_id=payload.quality_id)
    jobs.update(job.id, title=result.title)
    runner.spawn(job)
    return JobCreatedResponse(
        job_id=job.id,
        status=JobStatus.queued,
        poll_url=f"/api/v1/jobs/{job.id}",
        events_url=f"/api/v1/jobs/{job.id}/events",
        file_url=f"/api/v1/jobs/{job.id}/file",
    )
