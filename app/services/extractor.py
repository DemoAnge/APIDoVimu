from __future__ import annotations

from typing import Any, Protocol

import yt_dlp

from app.config import Settings
from app.core.exceptions import ExtractionError
from app.core.urls import hostname_of
from app.services.ffmpeg import detect_ffmpeg


class MediaExtractor(Protocol):
    def inspect(self, url: str, playlist: bool = False) -> dict: ...
    def search(self, query: str, limit: int = 10) -> dict: ...


def _base_opts(settings: Settings) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "no_color": True,
        "skip_download": True,
        "socket_timeout": settings.socket_timeout,
        "retries": 2,
        "extract_flat": False,
    }
    ffmpeg = detect_ffmpeg(settings)
    if ffmpeg:
        opts["ffmpeg_location"] = str(ffmpeg)
    if settings.cookies_file:
        opts["cookiefile"] = settings.cookies_file
    if settings.proxy:
        opts["proxy"] = settings.proxy
    return opts


class YtDlpExtractor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def inspect(self, url: str, playlist: bool = False) -> dict:
        opts = _base_opts(self._settings)
        opts["noplaylist"] = not playlist
        if playlist:
            opts["extract_flat"] = "in_playlist"
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise ExtractionError(
                f"No se pudo leer este enlace ({hostname_of(url)})."
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError("No se pudo extraer información de este enlace.") from exc
        if not info:
            raise ExtractionError("El enlace no devolvió información.")
        return info

    def search(self, query: str, limit: int = 10) -> dict:
        limit = max(1, min(limit, 20))
        opts = _base_opts(self._settings)
        opts["extract_flat"] = True
        opts["noplaylist"] = True
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise ExtractionError("La búsqueda no está disponible ahora mismo.") from exc
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError("No se pudo completar la búsqueda.") from exc
        return info or {"_type": "playlist", "entries": []}
