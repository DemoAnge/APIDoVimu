from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.config import Settings


def _win_candidates() -> list[Path]:
    local = os.environ.get("LOCALAPPDATA") or ""
    return [
        Path(local) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe",
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files\Gyan\FFmpeg\bin\ffmpeg.exe"),
    ]


def _from_imageio() -> str | None:
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    if exe and Path(exe).is_file():
        return exe
    return None


def detect_ffmpeg(settings: Settings | None = None) -> str | None:
    if settings and settings.ffmpeg_location:
        path = Path(settings.ffmpeg_location)
        if path.is_file():
            return str(path)
        for name in ("ffmpeg.exe", "ffmpeg"):
            candidate = path / name
            if candidate.is_file():
                return str(candidate)
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in _win_candidates():
        if candidate.is_file():
            return str(candidate)
    return _from_imageio()


def ffmpeg_available(settings: Settings | None = None) -> bool:
    return detect_ffmpeg(settings) is not None
