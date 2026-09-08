from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Protocol

import yt_dlp

from app.config import Settings
from app.core.exceptions import CancelledByUser, DownloadFailedError, MediaTooLargeError
from app.models.schemas import JobStatus
from app.services.ffmpeg import detect_ffmpeg
from app.services.jobs import Job, JobStore
from app.services.lyrics import enrich_lyrics
from app.services.quality import MEDIA_EXTS, build_ydl_plan, mime_for_path, parse_quality_id
from app.services.tags import collect_tags, embed_tags, pretty_filename, resolve_cover

logger = logging.getLogger(__name__)


class MediaDownloader(Protocol):
    def download(self, job: Job, dest_dir: Path) -> Path: ...


class YtDlpDownloader:
    def __init__(self, settings: Settings, jobs: JobStore, ffmpeg: bool) -> None:
        self._settings = settings
        self._jobs = jobs
        self._ffmpeg = ffmpeg

    def download(self, job: Job, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        selector, postprocessors, merge_format = build_ydl_plan(job.quality_id, self._ffmpeg)

        def hook(data: dict) -> None:
            current = self._jobs.get(job.id)
            if current is None or current.cancelled:
                raise CancelledByUser()
            status = data.get("status")
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                done = data.get("downloaded_bytes") or 0
                if total and total > self._settings.max_file_bytes:
                    raise MediaTooLargeError("El archivo supera el tamaño máximo permitido.")
                percent = min(99.0, (done / total) * 100) if total else 0.0
                eta = data.get("eta")
                self._jobs.update(
                    job.id,
                    status=JobStatus.downloading,
                    progress=percent,
                    speed_bytes=data.get("speed"),
                    eta_seconds=int(eta) if eta is not None else None,
                )
            elif status == "finished":
                self._jobs.update(
                    job.id,
                    status=JobStatus.processing,
                    progress=99.0,
                    speed_bytes=None,
                    eta_seconds=None,
                )

        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "no_color": True,
            "format": selector,
            "outtmpl": str(dest_dir / "%(title).80s.%(ext)s"),
            "windowsfilenames": True,
            "overwrites": True,
            "retries": 3,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": 8,
            "socket_timeout": self._settings.socket_timeout,
            "progress_hooks": [hook],
            "noplaylist": True,
            "format_sort": ["res", "fps", "vcodec:h264", "acodec:aac", "br"],
        }
        ffmpeg = detect_ffmpeg(self._settings)
        if ffmpeg:
            opts["ffmpeg_location"] = str(ffmpeg)
        if merge_format:
            opts["merge_output_format"] = merge_format
        extras = list(postprocessors or [])
        parsed = parse_quality_id(job.quality_id)
        is_audio = parsed.kind == "audio"
        if ffmpeg:
            opts["writethumbnail"] = True
            extras.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg"})
            extras.append({"key": "FFmpegMetadata", "add_metadata": True})
        if is_audio:
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = ["es", "es.*", "en", "en.*"]
            opts["subtitlesformat"] = "vtt/srt/best"
        if extras:
            opts["postprocessors"] = extras
        if self._settings.cookies_file:
            opts["cookiefile"] = self._settings.cookies_file
        if self._settings.proxy:
            opts["proxy"] = self._settings.proxy

        info: dict = {}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(job.url, download=True) or {}
        except CancelledByUser:
            raise
        except MediaTooLargeError:
            raise
        except yt_dlp.utils.DownloadError as exc:
            if _pick_output_file(dest_dir) is None:
                logger.warning("download failed job=%s", job.id)
                raise DownloadFailedError("No se pudo descargar este medio.") from exc
            logger.warning("yt-dlp falló en postproceso, se conserva el archivo job=%s", job.id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("download crashed job=%s", job.id)
            raise DownloadFailedError("Error inesperado durante la descarga.") from exc

        path = _pick_output_file(dest_dir)
        if path is None:
            raise DownloadFailedError("La descarga terminó pero no se encontró el archivo.")
        tags = collect_tags(info)
        tags.lyrics = enrich_lyrics(
            tags.lyrics,
            info,
            dest_dir,
            title=tags.title,
            artist=tags.artist,
            album=tags.album,
            duration=tags.duration_seconds,
            catalog=is_audio,
        )
        if is_audio and not tags.lyrics:
            logger.warning("sin letra job=%s", job.id)
        cover = resolve_cover(info, dest_dir)
        if cover is None:
            logger.warning("sin portada job=%s", job.id)
        embedded = False
        try:
            embedded = embed_tags(path, tags, cover)
        except Exception:
            logger.exception("no se pudieron incrustar metadatos job=%s", job.id)
            if cover is not None:
                try:
                    embedded = embed_tags(path, tags, None)
                except Exception:
                    logger.exception("tampoco se pudieron incrustar tags de texto job=%s", job.id)
        path = _rename_pretty(path, tags)
        self._jobs.update(
            job.id,
            title=tags.title or info.get("title"),
            metadata=tags.to_schema(embedded=embedded),
        )
        return path


def _pick_output_file(dest_dir: Path) -> Path | None:
    files = [
        path
        for path in dest_dir.iterdir()
        if path.is_file() and path.suffix.lower() in MEDIA_EXTS and not path.name.endswith(".part")
    ]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_size)


def _rename_pretty(path: Path, tags) -> Path:
    target = path.with_name(pretty_filename(tags, path.suffix))
    if target == path:
        return path
    if target.exists():
        target = target.with_stem(f"{target.stem} {path.stem[-8:]}")
    try:
        return path.replace(target)
    except OSError:
        logger.warning("no se pudo renombrar %s", path.name)
        return path


class DownloadRunner:
    def __init__(
        self,
        settings: Settings,
        jobs: JobStore,
        downloader: MediaDownloader,
        semaphore: asyncio.Semaphore,
    ) -> None:
        self._settings = settings
        self._jobs = jobs
        self._downloader = downloader
        self._semaphore = semaphore
        self.tasks: set[asyncio.Task] = set()

    def spawn(self, job: Job) -> None:
        task = asyncio.create_task(self._run(job), name=f"download-{job.id}")
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _run(self, job: Job) -> None:
        dest_dir = self._settings.download_dir / job.id
        async with self._semaphore:
            current = self._jobs.get(job.id)
            if current is None or current.cancelled:
                self._jobs.update(job.id, status=JobStatus.cancelled)
                return
            self._jobs.update(job.id, status=JobStatus.downloading)
            try:
                path = await asyncio.to_thread(self._downloader.download, job, dest_dir)
            except CancelledByUser:
                self._jobs.update(job.id, status=JobStatus.cancelled, error="Cancelado")
                return
            except MediaTooLargeError as exc:
                self._jobs.update(job.id, status=JobStatus.failed, error=exc.message, progress=0)
                return
            except DownloadFailedError as exc:
                self._jobs.update(job.id, status=JobStatus.failed, error=exc.message, progress=0)
                return
            except Exception:  # noqa: BLE001
                logger.exception("job failed id=%s", job.id)
                self._jobs.update(
                    job.id,
                    status=JobStatus.failed,
                    error="Error inesperado durante la descarga.",
                    progress=0,
                )
                return

            size = path.stat().st_size if path.exists() else None
            if size and size > self._settings.max_file_bytes:
                self._jobs.update(
                    job.id,
                    status=JobStatus.failed,
                    error="El archivo supera el tamaño máximo permitido.",
                )
                return
            self._jobs.update(
                job.id,
                status=JobStatus.ready,
                progress=100.0,
                filepath=path,
                filename=path.name,
                mime=mime_for_path(path),
                filesize_bytes=size,
                speed_bytes=None,
                eta_seconds=None,
            )
