from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import FFmpegRequiredError, QualityNotAvailableError
from app.core.formatters import pretty_size
from app.models.schemas import QualityOption

MP3_BITRATES = (128, 192, 320)
STANDARD_HEIGHTS = (144, 240, 360, 480, 720, 1080, 1440, 2160)
MEDIA_EXTS = {".mp4", ".webm", ".mkv", ".mp3", ".m4a", ".opus", ".ogg", ".wav", ".aac", ".mov"}

_MIME = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".opus": "audio/ogg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}

_HEIGHT_LABELS = {
    2160: "2160p 4K",
    1440: "1440p 2K",
    1080: "1080p Full HD",
    720: "720p HD",
    480: "480p",
    360: "360p",
    240: "240p",
    144: "144p",
}


@dataclass(frozen=True)
class ParsedQuality:
    kind: str
    height: int | None = None
    codec: str | None = None
    abr: int | None = None
    fps: int | None = None
    raw_id: str = ""


def parse_quality_id(quality_id: str) -> ParsedQuality:
    if not quality_id:
        raise QualityNotAvailableError("Debes elegir una calidad.")
    parts = quality_id.strip().split(":")
    if parts[0] == "video" and 2 <= len(parts) <= 3 and parts[1].isdigit():
        height = int(parts[1])
        if height < 144 or height > 4320:
            raise QualityNotAvailableError("Esa resolución no es válida.")
        fps = int(parts[2]) if len(parts) == 3 and parts[2].isdigit() else None
        return ParsedQuality(kind="video", height=height, fps=fps, raw_id=quality_id)
    if quality_id == "audio:best":
        return ParsedQuality(kind="audio", codec="original", raw_id=quality_id)
    if len(parts) == 3 and parts[0] == "audio" and parts[1] == "mp3" and parts[2].isdigit():
        abr = int(parts[2])
        if abr not in MP3_BITRATES:
            raise QualityNotAvailableError("Ese bitrate de MP3 no está disponible.")
        return ParsedQuality(kind="audio", codec="mp3", abr=abr, raw_id=quality_id)
    raise QualityNotAvailableError("El identificador de calidad no es válido.")


def mime_for_path(path) -> str:
    suffix = str(path).rsplit(".", 1)
    ext = f".{suffix[-1].lower()}" if len(suffix) == 2 else ""
    return _MIME.get(ext, "application/octet-stream")


def snap_height(height: int) -> int:
    nearest = min(STANDARD_HEIGHTS, key=lambda item: abs(item - height))
    if abs(nearest - height) <= 16:
        return nearest
    return height


def _is_video(fmt: dict) -> bool:
    vcodec = fmt.get("vcodec")
    return bool(vcodec) and vcodec != "none"


def _is_audio(fmt: dict) -> bool:
    acodec = fmt.get("acodec")
    return bool(acodec) and acodec != "none"


def _is_progressive(fmt: dict) -> bool:
    return _is_video(fmt) and _is_audio(fmt)


def _filesize(fmt: dict) -> int | None:
    value = fmt.get("filesize") or fmt.get("filesize_approx")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _estimate_size(fmt: dict, duration: int | None, extra: int | None = None) -> int | None:
    size = _filesize(fmt)
    if size is None:
        tbr = fmt.get("tbr") or fmt.get("vbr")
        if tbr and duration:
            try:
                size = int(float(tbr) * 1000 / 8 * duration)
            except (TypeError, ValueError):
                size = None
    if size is None:
        return extra
    if extra:
        return size + extra
    return size


def _fps_bucket(fmt: dict) -> int:
    fps = fmt.get("fps") or 0
    try:
        value = float(fps)
    except (TypeError, ValueError):
        return 30
    return 60 if value >= 50 else 30


def _codec_label(fmt: dict) -> str:
    vcodec = str(fmt.get("vcodec") or "").lower()
    if "avc" in vcodec or "h264" in vcodec:
        return "H.264"
    if "av01" in vcodec or "av1" in vcodec:
        return "AV1"
    if "vp9" in vcodec or "vp09" in vcodec:
        return "VP9"
    if "hev" in vcodec or "h265" in vcodec:
        return "H.265"
    return (fmt.get("ext") or "mp4").upper()


def _score_video(fmt: dict) -> tuple:
    tbr = fmt.get("tbr") or fmt.get("vbr") or 0
    fps = fmt.get("fps") or 0
    vcodec = str(fmt.get("vcodec") or "")
    ext = fmt.get("ext") or ""
    avc = 2 if "avc" in vcodec else 0
    mp4 = 1 if ext == "mp4" else 0
    hdr = 1 if str(fmt.get("dynamic_range") or "").upper().startswith("HDR") else 0
    return (float(tbr), float(fps), hdr, avc, mp4)


def _score_audio(fmt: dict) -> tuple:
    ext = fmt.get("ext") or ""
    abr = fmt.get("abr") or fmt.get("tbr") or 0
    pref = {"m4a": 3, "aac": 3, "mp3": 2, "webm": 1, "opus": 1}.get(ext, 0)
    return (float(abr), pref)


def video_label(height: int, fps_bucket: int | None) -> str:
    base = _HEIGHT_LABELS.get(height, f"{height}p")
    if fps_bucket and fps_bucket >= 50:
        return f"{base} 60fps"
    return base


def video_format_selector(height: int, ffmpeg: bool, fps: int | None = None) -> str:
    fps_filter = ""
    if fps and fps >= 50:
        fps_filter = "[fps>=50]"
    elif fps:
        fps_filter = "[fps<50]"
    if ffmpeg:
        return (
            f"bv*[height={height}]{fps_filter}[vcodec^=avc1]+ba[ext=m4a]/"
            f"bv*[height={height}]{fps_filter}[ext=mp4]+ba[ext=m4a]/"
            f"bv*[height={height}]{fps_filter}+ba/"
            f"b[height={height}]{fps_filter}[ext=mp4]/"
            f"b[height={height}]{fps_filter}/"
            f"bv*[height<={height}][vcodec^=avc1]+ba[ext=m4a]/"
            f"bv*[height<={height}]+ba/"
            f"b[height<={height}]"
        )
    return (
        f"b[height={height}]{fps_filter}[ext=mp4]/"
        f"b[height={height}]{fps_filter}/"
        f"b[height<={height}][ext=mp4]/"
        f"b[height<={height}]"
    )


def audio_format_selector(parsed: ParsedQuality) -> tuple[str, list[dict] | None]:
    if parsed.codec == "original":
        return "ba[ext=m4a]/bestaudio[ext=m4a]/bestaudio/ba/b", None
    if parsed.codec == "mp3" and parsed.abr:
        return "bestaudio/ba/b", [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(parsed.abr),
            }
        ]
    raise QualityNotAvailableError("El identificador de calidad no es válido.")


def build_ydl_plan(quality_id: str, ffmpeg: bool) -> tuple[str, list[dict] | None, str | None]:
    parsed = parse_quality_id(quality_id)
    if parsed.kind == "video" and parsed.height is not None:
        return video_format_selector(parsed.height, ffmpeg, parsed.fps), None, "mp4" if ffmpeg else None
    if parsed.kind == "audio":
        if parsed.codec == "mp3" and not ffmpeg:
            raise FFmpegRequiredError(
                "Para exportar MP3 hace falta FFmpeg. Instálalo o elige audio original."
            )
        selector, post = audio_format_selector(parsed)
        return selector, post, None
    raise QualityNotAvailableError("El identificador de calidad no es válido.")


def _best_audio(formats: list[dict]) -> dict | None:
    audios = [f for f in formats if _is_audio(f) and not _is_video(f)]
    if not audios:
        return None
    return max(audios, key=_score_audio)


def _mark_recommended(options: list[QualityOption]) -> list[QualityOption]:
    if not options:
        return options
    pick = next((item for item in options if item.height == 1080 and (item.fps or 30) < 50), None)
    if pick is None:
        pick = next((item for item in options if item.height == 1080), None)
    if pick is None:
        pick = next((item for item in options if item.height == 720), None)
    if pick is None:
        pick = options[0]
    return [
        item.model_copy(update={"recommended": True}) if item.id == pick.id else item
        for item in options
    ]


def build_video_qualities(
    formats: list[dict],
    ffmpeg: bool,
    duration: int | None = None,
) -> list[QualityOption]:
    groups: dict[tuple[int, int], list[dict]] = {}
    for fmt in formats:
        if not _is_video(fmt):
            continue
        height = fmt.get("height")
        if not height:
            continue
        key = (snap_height(int(height)), _fps_bucket(fmt))
        groups.setdefault(key, []).append(fmt)

    buckets_by_height: dict[int, list[int]] = {}
    for height, fps_bucket in groups:
        buckets_by_height.setdefault(height, []).append(fps_bucket)

    best_audio = _best_audio(formats)
    audio_size = _filesize(best_audio) if best_audio else None
    options: list[QualityOption] = []

    for height, fps_bucket in sorted(groups, key=lambda item: (item[0], item[1]), reverse=True):
        group = groups[(height, fps_bucket)]
        eligible = [f for f in group if ffmpeg or _is_progressive(f)]
        if not eligible:
            continue
        best = max(eligible, key=_score_video)
        needs_merge = ffmpeg and not _is_progressive(best)
        extra = audio_size if needs_merge else None
        size = _estimate_size(best, duration, extra)
        ext = "mp4" if ffmpeg or best.get("ext") == "mp4" else (best.get("ext") or "mp4")
        fps = best.get("fps")
        many_fps = len(set(buckets_by_height.get(height, []))) > 1
        quality_id = f"video:{height}:{fps_bucket}" if many_fps else f"video:{height}"
        note_parts = [ext.upper(), _codec_label(best)]
        if fps:
            note_parts.append(f"{int(fps)} fps")
        options.append(
            QualityOption(
                id=quality_id,
                kind="video",
                label=video_label(height, fps_bucket if many_fps or fps_bucket >= 50 else None),
                ext=ext,
                height=height,
                width=best.get("width"),
                fps=float(fps) if fps else float(fps_bucket),
                filesize_bytes=size,
                filesize_label=pretty_size(size),
                note=" · ".join(note_parts),
                needs_ffmpeg=needs_merge,
            )
        )
    return _mark_recommended(options)


def build_audio_qualities(formats: list[dict], ffmpeg: bool, duration: int | None) -> list[QualityOption]:
    options: list[QualityOption] = []
    best = _best_audio(formats)
    if best:
        size = _filesize(best)
        ext = best.get("ext") or "m4a"
        abr = best.get("abr") or best.get("tbr")
        abr_i = int(abr) if abr else None
        label = "Mejor calidad"
        if abr_i:
            label = f"Mejor calidad ({abr_i} kbps)"
        options.append(
            QualityOption(
                id="audio:best",
                kind="audio",
                label=label,
                ext=ext,
                abr=abr_i,
                filesize_bytes=size,
                filesize_label=pretty_size(size),
                note=ext.upper(),
                needs_ffmpeg=False,
                recommended=True,
            )
        )
    elif any(_is_progressive(f) for f in formats):
        options.append(
            QualityOption(
                id="audio:best",
                kind="audio",
                label="Mejor calidad",
                ext="m4a",
                note="extraído del video",
                needs_ffmpeg=False,
                recommended=True,
            )
        )

    if ffmpeg:
        for bitrate in reversed(MP3_BITRATES):
            estimated = int(duration * bitrate * 1000 / 8) if duration else None
            options.append(
                QualityOption(
                    id=f"audio:mp3:{bitrate}",
                    kind="audio",
                    label=f"MP3 {bitrate} kbps",
                    ext="mp3",
                    abr=bitrate,
                    filesize_bytes=estimated,
                    filesize_label=pretty_size(estimated),
                    note="MP3",
                    needs_ffmpeg=True,
                )
            )
    return options


def build_qualities(
    formats: list[dict] | None,
    ffmpeg: bool,
    duration: int | None = None,
) -> tuple[list[QualityOption], list[QualityOption]]:
    formats = formats or []
    return (
        build_video_qualities(formats, ffmpeg, duration),
        build_audio_qualities(formats, ffmpeg, duration),
    )
