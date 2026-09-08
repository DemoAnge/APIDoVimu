from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_MAX_LYRICS = 50_000
_SUB_EXTS = {".lrc", ".vtt", ".srt"}
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_LRCLIB_UA = "DoVimu/1.0 (personal music library)"
_HEADER = re.compile(
    r"(?im)^\s*(?:letra(?:s)?(?:\s+de(?:l| la)?(?:\s+tema|\s+canci[oó]n)?)?|lyrics)\s*:?\s*$"
)
_CUT = re.compile(
    r"(?im)^\s*(https?://|www\.|subscribe|suscr[ií]bete|s[ií]gueme|follow me|spotify|itunes)\b"
)
_VTT_TS = re.compile(
    r"^(?:(\d{2}):)?(\d{2}):(\d{2})[\.,](\d{3})\s+-->"
)
_TAG = re.compile(r"<[^>]+>")
_LANG_RANK = {
    "es": 0,
    "es-orig": 1,
    "es-419": 2,
    "es-mx": 3,
    "es-es": 4,
    "en": 10,
    "en-orig": 11,
    "en-us": 12,
    "en-gb": 13,
}


def lyrics_from_info_fields(info: dict) -> str | None:
    explicit = _clean(_as_text(info.get("lyrics") or info.get("track_lyrics")), require_structure=False)
    if explicit:
        return explicit
    return _from_description(_as_text(info.get("description")))


def enrich_lyrics(
    existing: str | None,
    info: dict,
    dest_dir: Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    duration: int | None = None,
    catalog: bool = False,
) -> str | None:
    text = _clean(existing, require_structure=False)
    if text:
        return text
    text = lyrics_from_info_fields(info)
    if text:
        return text
    text = lyrics_from_sidecars(dest_dir)
    if text:
        return text
    text = lyrics_from_subtitle_map(info.get("subtitles") or {})
    if text:
        return text
    text = lyrics_from_subtitle_map(info.get("automatic_captions") or {})
    if text:
        return text
    if catalog:
        text = fetch_catalog_lyrics(title=title, artist=artist, album=album, duration=duration)
        if text:
            return text
    return None


def lyrics_from_sidecars(dest_dir: Path) -> str | None:
    if not dest_dir.is_dir():
        return None
    files = [
        path
        for path in dest_dir.iterdir()
        if path.is_file() and path.suffix.lower() in _SUB_EXTS
    ]
    files.sort(key=_sidecar_rank)
    for path in files:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parsed = parse_subtitle_text(raw, path.suffix.lower())
        if parsed:
            return parsed
    return None


def lyrics_from_subtitle_map(mapping) -> str | None:
    if not isinstance(mapping, dict) or not mapping:
        return None
    for lang, _rank in sorted(_LANG_RANK.items(), key=lambda item: item[1]):
        tracks = mapping.get(lang)
        parsed = _tracks_to_lyrics(tracks)
        if parsed:
            return parsed
    ranked: list[tuple[int, str, object]] = []
    for lang, tracks in mapping.items():
        ranked.append((_LANG_RANK.get(str(lang).lower(), 80), str(lang), tracks))
    ranked.sort(key=lambda item: item[0])
    for _rank, _lang, tracks in ranked:
        parsed = _tracks_to_lyrics(tracks)
        if parsed:
            return parsed
    return None


def parse_subtitle_text(raw: str, suffix: str) -> str | None:
    suffix = suffix.lower()
    if suffix == ".lrc":
        parsed = raw
    elif suffix in {".vtt", ".srt"}:
        parsed = vtt_to_lrc(raw)
    elif suffix in {".json3", ".json"}:
        parsed = json3_to_lrc(raw)
    else:
        parsed = raw
    return _clean(parsed, require_structure=False)


def vtt_to_lrc(raw: str) -> str | None:
    lines: list[str] = []
    last = None
    stamp = None
    for original in raw.replace("\r\n", "\n").split("\n"):
        line = original.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("WEBVTT") or upper.startswith("NOTE") or upper.startswith("STYLE") or upper.startswith("KIND:") or upper.startswith("LANGUAGE:"):
            continue
        match = _VTT_TS.match(line)
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2)) + hours * 60
            seconds = match.group(3)
            hundredths = match.group(4)[:2]
            stamp = f"[{minutes:02d}:{seconds}.{hundredths}]"
            continue
        if "-->" in line:
            continue
        if line.isdigit():
            continue
        text = _TAG.sub("", line).replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()
        if not text or text == last:
            continue
        last = text
        lines.append(f"{stamp}{text}" if stamp else text)
    return "\n".join(lines) if lines else None


def json3_to_lrc(raw: str) -> str | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    events = payload.get("events") or []
    lines: list[str] = []
    last = None
    for event in events:
        segs = event.get("segs") or []
        text = "".join(str(seg.get("utf8") or "") for seg in segs).replace("\n", " ").strip()
        if not text or text == last:
            continue
        last = text
        start = int(event.get("tStartMs") or 0)
        minutes, rest = divmod(start, 60_000)
        seconds, millis = divmod(rest, 1000)
        lines.append(f"[{minutes:02d}:{seconds:02d}.{millis // 10:02d}]{text}")
    return "\n".join(lines) if lines else None


def fetch_catalog_lyrics(
    title: str | None,
    artist: str | None,
    album: str | None = None,
    duration: int | None = None,
) -> str | None:
    if not title or not artist:
        return None
    params = {"track_name": title, "artist_name": artist}
    if album:
        params["album_name"] = album
    if duration:
        params["duration"] = int(duration)
    url = "https://lrclib.net/api/get?" + urlencode(params)
    try:
        req = Request(url, headers={"User-Agent": _LRCLIB_UA, "Accept": "application/json"})
        with urlopen(req, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        if exc.code != 404:
            logger.warning("catálogo de letras no disponible (%s)", exc.code)
        return None
    except Exception:
        logger.warning("no se pudo consultar la letra")
        return None
    if not isinstance(payload, dict):
        return None
    return _clean(payload.get("syncedLyrics") or payload.get("plainLyrics"), require_structure=False)


def _from_description(description: str | None) -> str | None:
    if not description:
        return None
    match = _HEADER.search(description)
    if not match:
        return None
    body = description[match.end() :].strip()
    cut = _CUT.search(body)
    if cut and cut.start() > 40:
        body = body[: cut.start()].strip()
    return _clean(body)


def _tracks_to_lyrics(tracks) -> str | None:
    if not tracks:
        return None
    if isinstance(tracks, dict):
        tracks = [tracks]
    if not isinstance(tracks, list):
        return None
    preferred = {"vtt": 0, "srt": 1, "lrc": 2, "json3": 3, "srv3": 4}
    ordered = sorted(
        [item for item in tracks if isinstance(item, dict) and item.get("url")],
        key=lambda item: preferred.get(str(item.get("ext") or "").lower(), 9),
    )
    for item in ordered:
        ext = "." + str(item.get("ext") or "vtt").lower().lstrip(".")
        raw = _download_text(item["url"])
        if not raw:
            continue
        parsed = parse_subtitle_text(raw, ext)
        if parsed:
            return parsed
    return None


def _download_text(url: str) -> str | None:
    try:
        req = Request(
            url,
            headers={
                "User-Agent": _BROWSER_UA,
                "Accept": "text/vtt,application/json,text/plain,*/*",
                "Referer": "https://www.youtube.com/",
            },
        )
        with urlopen(req, timeout=15) as response:
            data = response.read(512_000)
        if not data:
            return None
        return data.decode("utf-8", errors="replace")
    except Exception:
        logger.warning("no se pudo bajar la pista de letra")
        return None


def _sidecar_rank(path: Path) -> tuple:
    name = path.name.lower()
    ext_rank = {".lrc": 0, ".vtt": 1, ".srt": 2}.get(path.suffix.lower(), 9)
    lang_rank = 50
    for lang, rank in _LANG_RANK.items():
        token = f".{lang}."
        if token in name or name.endswith(f".{lang}{path.suffix.lower()}"):
            lang_rank = rank
            break
    auto = 1 if "auto" in name else 0
    return (ext_rank, auto, lang_rank)


def _as_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value if item]
        text = "\n".join(parts).strip()
        return text or None
    text = str(value).strip()
    return text or None


def _clean(text: str | None, require_structure: bool = True) -> str | None:
    if not text:
        return None
    cleaned = text.replace("\r\n", "\n").strip()
    if len(cleaned) > _MAX_LYRICS:
        cleaned = cleaned[:_MAX_LYRICS]
    if len(cleaned) < 12:
        return None
    if require_structure and not _looks_like_lyrics(cleaned):
        return None
    return cleaned


def _looks_like_lyrics(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 4:
        return False
    urls = sum(1 for line in lines if "http://" in line.lower() or "https://" in line.lower() or line.lower().startswith("www."))
    if urls > max(1, len(lines) // 4):
        return False
    avg = sum(len(line) for line in lines) / len(lines)
    return avg < 140
