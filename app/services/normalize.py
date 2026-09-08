from __future__ import annotations

from app.core.formatters import pretty_duration
from app.models.schemas import InspectResponse, PlaylistEntry, SearchResult
from app.services.quality import build_qualities
from app.services.tags import best_thumbnail_url, collect_tags


def _best_thumbnail(info: dict) -> str | None:
    return best_thumbnail_url(info)


def _duration(info: dict) -> int | None:
    value = info.get("duration")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source(info: dict) -> str:
    key = (
        info.get("extractor_key")
        or info.get("ie_key")
        or info.get("extractor")
        or "generic"
    )
    return str(key).lower()


def _entry_url(entry: dict) -> str | None:
    return (
        entry.get("webpage_url")
        or entry.get("url")
        or entry.get("original_url")
    )


def playlist_entries(info: dict, limit: int = 100) -> list[PlaylistEntry]:
    raw_entries = info.get("entries") or []
    items: list[PlaylistEntry] = []
    for entry in raw_entries:
        if not entry:
            continue
        duration = _duration(entry)
        items.append(
            PlaylistEntry(
                media_id=str(entry.get("id") or entry.get("url") or len(items)),
                title=entry.get("title") or "Sin título",
                url=_entry_url(entry),
                duration=duration,
                duration_label=pretty_duration(duration),
                thumbnail=_best_thumbnail(entry),
                uploader=entry.get("uploader") or entry.get("channel"),
            )
        )
        if len(items) >= limit:
            break
    return items


def normalize_media(info: dict, ffmpeg_available: bool) -> InspectResponse:
    is_playlist = info.get("_type") in {"playlist", "multi_video"}
    duration = _duration(info)
    video: list = []
    audio: list = []
    entries: list[PlaylistEntry] = []

    if is_playlist:
        entries = playlist_entries(info)
        title = info.get("title") or "Lista"
        media_id = str(info.get("id") or "playlist")
        webpage_url = info.get("webpage_url") or info.get("original_url") or ""
    else:
        video, audio = build_qualities(info.get("formats") or [], ffmpeg_available, duration)
        title = info.get("title") or "Sin título"
        media_id = str(info.get("id") or "")
        webpage_url = info.get("webpage_url") or info.get("original_url") or ""

    return InspectResponse(
        source=_source(info),
        extractor=str(info.get("extractor") or info.get("extractor_key") or "generic"),
        media_id=media_id,
        title=title,
        uploader=info.get("uploader") or info.get("channel"),
        duration=duration,
        duration_label=pretty_duration(duration),
        thumbnail=_best_thumbnail(info),
        webpage_url=webpage_url,
        description=info.get("description"),
        is_playlist=is_playlist,
        entries=entries,
        video=video,
        audio=audio,
        ffmpeg_available=ffmpeg_available,
        metadata=None if is_playlist else collect_tags(info).to_schema(),
    )


def normalize_search(info: dict, query: str) -> list[SearchResult]:
    entries = info.get("entries") or []
    results: list[SearchResult] = []
    for entry in entries:
        if not entry:
            continue
        duration = _duration(entry)
        url = _entry_url(entry)
        if url and not url.startswith("http") and entry.get("id"):
            url = f"https://www.youtube.com/watch?v={entry['id']}"
        results.append(
            SearchResult(
                media_id=str(entry.get("id") or ""),
                title=entry.get("title") or "Sin título",
                url=url,
                duration=duration,
                duration_label=pretty_duration(duration),
                thumbnail=_best_thumbnail(entry),
                uploader=entry.get("uploader") or entry.get("channel"),
                source=_source(entry) if entry.get("extractor_key") else "youtube",
            )
        )
    return results
