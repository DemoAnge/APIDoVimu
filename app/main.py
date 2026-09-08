from __future__ import annotations

import asyncio
import logging
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import health, jobs, media, search
from app.config import get_settings
from app.core.exceptions import AppError
from app.services.downloader import DownloadRunner, YtDlpDownloader
from app.services.extractor import YtDlpExtractor
from app.services.ffmpeg import ffmpeg_available
from app.services.jobs import JobStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("dovimu")


async def _cleanup_loop(app: FastAPI) -> None:
    settings = app.state.settings
    jobs: JobStore = app.state.jobs
    while True:
        await asyncio.sleep(60)
        for job in jobs.expired(settings.job_ttl_seconds):
            dest = settings.download_dir / job.id
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            jobs.pop(job.id)
            logger.info("expired job removed id=%s", job.id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    jobs = JobStore()
    has_ffmpeg = ffmpeg_available(settings)
    extractor = YtDlpExtractor(settings)
    downloader = YtDlpDownloader(settings, jobs, has_ffmpeg)
    semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)
    runner = DownloadRunner(settings, jobs, downloader, semaphore)

    app.state.settings = settings
    app.state.jobs = jobs
    app.state.extractor = extractor
    app.state.downloader = downloader
    app.state.runner = runner
    app.state.ffmpeg_available = has_ffmpeg
    app.state.cleanup_task = asyncio.create_task(_cleanup_loop(app))

    if not has_ffmpeg:
        logger.warning(
            "FFmpeg no está en PATH. Solo se ofrecerán videos progresivos (audio+video juntos) "
            "y audio original. Instala FFmpeg para 720p/1080p unidos y MP3."
        )
    logger.info("DoVimu API %s lista (ffmpeg=%s)", __version__, has_ffmpeg)
    try:
        yield
    finally:
        app.state.cleanup_task.cancel()
        for task in list(runner.tasks):
            task.cancel()


app = FastAPI(
    title="DoVimu API",
    description="API para inspeccionar y descargar video o audio desde un enlace, con varias calidades.",
    version=__version__,
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(media.router)
app.include_router(jobs.router)
app.include_router(search.router)


@app.get("/")
def root() -> dict:
    return {
        "name": "DoVimu API",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }


@app.exception_handler(AppError)
async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
