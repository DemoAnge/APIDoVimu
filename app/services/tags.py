from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from app.models.schemas import TrackMetadata
from app.services.ffmpeg import detect_ffmpeg

logger = logging.getLogger(__name__)

_COVER_NAME = "cover.jpg"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_INVALID_FILENAME = set('\\/:*?"<>|\n\r')
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_YT_ID_RE = re.compile(r"(?:v=|/shorts/|youtu\.be/)([A-Za-z0-9_-]{11})")


@dataclass
class TagPayload:
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    track: int | None = None
    genre: str | None = None
    year: str | None = None
    lyrics: str | None = None
    comment: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: int | None = None
    width: int | None = None
    height: int | None = None

    def to_schema(self, embedded: bool = False) -> TrackMetadata:
        return TrackMetadata(
            title=self.title,
            artist=self.artist,
            album=self.album,
            album_artist=self.album_artist,
            track=self.track,
            genre=self.genre,
            year=self.year,
            lyrics=self.lyrics,
            comment=self.comment,
            thumbnail=self.thumbnail_url,
            duration_seconds=self.duration_seconds,
            width=self.width,
            height=self.height,
            embedded=embedded,
        )


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or item.get("text")
                if name:
                    parts.append(str(name))
            elif item:
                parts.append(str(item))
        text = ", ".join(parts).strip()
        return text or None
    text = str(value).strip()
    return text or None


def humanize_text(value: str | None) -> str | None:
    """Turn yt-dlp restrictfilenames text into normal spaces."""
    if not value:
        return value
    text = value.strip()
    if "_-_" in text or (text.count("_") >= 2 and " " not in text):
        text = text.replace("_", " ")
    return " ".join(text.split()) or None


def _youtube_id(info: dict) -> str | None:
    extractor = str(info.get("extractor_key") or info.get("extractor") or "").lower()
    vid = str(info.get("id") or "")
    if vid and len(vid) == 11 and (not extractor or "youtube" in extractor):
        return vid
    url = str(info.get("webpage_url") or info.get("original_url") or info.get("thumbnail") or "")
    match = _YT_ID_RE.search(url)
    return match.group(1) if match else None


def thumbnail_candidates(info: dict) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    def add(url: str | None) -> None:
        if not url or url in seen:
            return
        lowered = url.lower()
        if "storyboard" in lowered or "/sb/" in lowered:
            return
        seen.add(url)
        ordered.append(url)

    thumbs = [t for t in (info.get("thumbnails") or []) if isinstance(t, dict) and t.get("url")]

    def score(thumb: dict) -> tuple:
        url = str(thumb.get("url") or "")
        width = thumb.get("width") or 0
        height = thumb.get("height") or 0
        lowered = url.lower()
        webp = ".webp" in lowered
        jpg = (not webp) and any(
            token in lowered for token in (".jpg", ".jpeg", "hqdefault", "sddefault", "mqdefault", "maxres")
        )
        return (0 if webp else 1, 1 if jpg else 0, int(width) * int(height))

    thumbs.sort(key=score, reverse=True)
    for thumb in thumbs:
        add(thumb.get("url"))
    add(info.get("thumbnail"))
    video_id = _youtube_id(info)
    if video_id:
        for name in ("maxresdefault.jpg", "sddefault.jpg", "hq720.jpg", "hqdefault.jpg", "mqdefault.jpg"):
            add(f"https://i.ytimg.com/vi/{video_id}/{name}")
    return ordered


def best_thumbnail_url(info: dict) -> str | None:
    urls = thumbnail_candidates(info)
    return urls[0] if urls else None


def _year(info: dict) -> str | None:
    for key in ("release_year", "release_date", "upload_date"):
        raw = info.get(key)
        if not raw:
            continue
        text = str(raw)
        if len(text) >= 4 and text[:4].isdigit():
            return text[:4]
    return None


def _parse_artist_title(title: str, artist: str | None) -> tuple[str | None, str]:
    if artist:
        return artist, title
    for sep in (" - ", " – ", " — "):
        if sep in title:
            left, right = title.split(sep, 1)
            if 1 < len(left.strip()) < 80 and right.strip():
                return left.strip(), right.strip()
    return artist, title


def collect_tags(info: dict) -> TagPayload:
    raw_title = humanize_text(_text(info.get("track") or info.get("title"))) or "Sin título"
    artist = humanize_text(
        _text(info.get("artist"))
        or _text(info.get("artists"))
        or _text(info.get("creator"))
    )
    if artist:
        title = raw_title
        if artist.lower() == title.lower():
            artist, title = _parse_artist_title(raw_title, None)
    else:
        artist, title = _parse_artist_title(raw_title, None)
    if not artist:
        artist = humanize_text(_text(info.get("uploader")) or _text(info.get("channel")))
    album = humanize_text(_text(info.get("album")))
    if not album:
        playlist = humanize_text(_text(info.get("playlist_title") or info.get("playlist")))
        try:
            count = int(info.get("playlist_count") or 0)
        except (TypeError, ValueError):
            count = 0
        if playlist and count > 1:
            album = playlist
    from app.services.lyrics import lyrics_from_info_fields

    lyrics = lyrics_from_info_fields(info)
    description = _text(info.get("description"))
    webpage = _text(info.get("webpage_url") or info.get("original_url"))
    comment_parts = [p for p in (webpage, description) if p]
    comment = "\n\n".join(comment_parts)[:4000] if comment_parts else None
    track = info.get("track_number") or info.get("playlist_index")
    try:
        track_n = int(track) if track is not None else None
    except (TypeError, ValueError):
        track_n = None
    duration = info.get("duration")
    try:
        duration_s = int(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_s = None
    width = info.get("width")
    height = info.get("height")
    try:
        width_i = int(width) if width else None
        height_i = int(height) if height else None
    except (TypeError, ValueError):
        width_i, height_i = None, None
    return TagPayload(
        title=title,
        artist=artist,
        album=album,
        album_artist=humanize_text(_text(info.get("album_artist"))) or artist,
        track=track_n,
        genre=_text(info.get("genre") or info.get("genres")),
        year=_year(info),
        lyrics=lyrics,
        comment=comment,
        thumbnail_url=best_thumbnail_url(info),
        duration_seconds=duration_s,
        width=width_i,
        height=height_i,
    )


def pretty_filename(tags: TagPayload, suffix: str) -> str:
    title = tags.title or "Sin título"
    artist = tags.artist
    if artist and artist.lower() not in title.lower():
        stem = f"{artist} - {title}"
    else:
        stem = title
    cleaned = "".join(" " if ch in _INVALID_FILENAME else ch for ch in stem)
    cleaned = " ".join(cleaned.split())[:120] or "dovimu"
    ext = suffix if suffix.startswith(".") else f".{suffix}"
    return cleaned + ext.lower()


def _local_cover_files(dest_dir: Path) -> list[Path]:
    if not dest_dir.is_dir():
        return []
    rank = {".jpg": 0, ".jpeg": 1, ".png": 2, ".webp": 3, ".gif": 4}
    files = [
        path
        for path in dest_dir.iterdir()
        if path.is_file() and path.suffix.lower() in _IMAGE_EXTS
    ]
    files.sort(key=lambda p: (rank.get(p.suffix.lower(), 9), -p.stat().st_size))
    return files


def _http_get_bytes(url: str) -> bytes | None:
    try:
        req = Request(
            url,
            headers={
                "User-Agent": _BROWSER_UA,
                "Accept": "image/avif,image/webp,image/apng,image/jpeg,image/png,image/*,*/*;q=0.8",
                "Referer": "https://www.youtube.com/",
            },
        )
        with urlopen(req, timeout=20) as response:
            data = response.read()
        if not data or len(data) < 200:
            return None
        head = data[:32].lstrip().lower()
        if head.startswith(b"<!doctype") or head.startswith(b"<html"):
            return None
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("no se pudo bajar la portada (%s)", type(exc).__name__)
        return None


def _is_jpeg(data: bytes) -> bool:
    return data.startswith(b"\xff\xd8")


def _is_png(data: bytes) -> bool:
    return data.startswith(b"\x89PNG\r\n\x1a\n")


def _to_jpeg(data: bytes, dest_dir: Path) -> bytes | None:
    if _is_jpeg(data):
        return data
    if _is_png(data):
        return data
    ffmpeg = detect_ffmpeg()
    if not ffmpeg:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    src = dest_dir / "cover.bin"
    out = dest_dir / _COVER_NAME
    try:
        src.write_bytes(data)
        subprocess.run(
            [ffmpeg, "-y", "-i", str(src), "-frames:v", "1", "-q:v", "2", str(out)],
            check=True,
            capture_output=True,
            timeout=30,
        )
        if out.is_file() and out.stat().st_size > 200:
            converted = out.read_bytes()
            if _is_jpeg(converted):
                return converted
    except Exception:
        logger.warning("no se pudo convertir la portada a JPEG")
    finally:
        src.unlink(missing_ok=True)
    return None


def fetch_cover(url: str | None, dest_dir: Path) -> bytes | None:
    if not url:
        return None
    data = _http_get_bytes(url)
    if not data:
        return None
    return _to_jpeg(data, dest_dir)


def resolve_cover(info: dict, dest_dir: Path) -> bytes | None:
    best: bytes | None = None
    for path in _local_cover_files(dest_dir):
        try:
            converted = _to_jpeg(path.read_bytes(), dest_dir)
        except OSError:
            continue
        if converted and (best is None or len(converted) > len(best)):
            best = converted
            if len(best) > 12_000:
                return best
    for url in thumbnail_candidates(info):
        data = _http_get_bytes(url)
        if not data:
            continue
        converted = _to_jpeg(data, dest_dir)
        if converted and (best is None or len(converted) > len(best)):
            best = converted
            if len(best) > 20_000:
                break
    return best


def embed_tags(path: Path, tags: TagPayload, cover: bytes | None) -> bool:
    suffix = path.suffix.lower()
    jpeg = _to_jpeg(cover, path.parent) if cover else None
    if suffix in {".mp3", ".mp2"}:
        return _embed_mp3(path, tags, jpeg)
    if suffix in {".m4a", ".mp4", ".aac", ".m4b"}:
        return _embed_mp4(path, tags, jpeg)
    if suffix in {".ogg", ".opus", ".flac"}:
        return _embed_vorbis(path, tags, jpeg)
    return False


def _cover_mime(data: bytes) -> str:
    if _is_png(data):
        return "image/png"
    return "image/jpeg"


def _embed_mp3(path: Path, tags: TagPayload, cover: bytes | None) -> bool:
    from mutagen.id3 import (
        APIC,
        COMM,
        ID3,
        TALB,
        TCON,
        TIT2,
        TPE1,
        TPE2,
        TRCK,
        TYER,
        TXXX,
        USLT,
        WOAR,
        Encoding,
        ID3NoHeaderError,
    )
    from mutagen.mp3 import HeaderNotFoundError, MP3

    try:
        audio = MP3(path)
    except HeaderNotFoundError:
        header = ID3()
        header.save(path)
        audio = MP3(path)
    if audio.tags is None:
        try:
            audio.add_tags()
        except Exception:
            try:
                ID3(path)
            except ID3NoHeaderError:
                tags_header = ID3()
                tags_header.save(path)
            audio = MP3(path)
    id3 = audio.tags
    if id3 is None:
        raise RuntimeError("no se pudo crear el encabezado ID3")
    if tags.title:
        id3["TIT2"] = TIT2(encoding=Encoding.UTF8, text=tags.title)
    if tags.artist:
        id3["TPE1"] = TPE1(encoding=Encoding.UTF8, text=tags.artist)
    if tags.album:
        id3["TALB"] = TALB(encoding=Encoding.UTF8, text=tags.album)
    if tags.album_artist:
        id3["TPE2"] = TPE2(encoding=Encoding.UTF8, text=tags.album_artist)
    if tags.year:
        id3["TYER"] = TYER(encoding=Encoding.UTF8, text=tags.year)
    if tags.genre:
        id3["TCON"] = TCON(encoding=Encoding.UTF8, text=tags.genre)
    if tags.track:
        id3["TRCK"] = TRCK(encoding=Encoding.UTF8, text=str(tags.track))
    if tags.comment:
        id3["COMM"] = COMM(encoding=Encoding.UTF8, lang="eng", desc="", text=tags.comment)
    if tags.lyrics:
        id3.delall("USLT")
        id3.add(USLT(encoding=Encoding.UTF16, lang="und", desc="", text=tags.lyrics))
        id3.add(TXXX(encoding=Encoding.UTF16, desc="LYRICS", text=[tags.lyrics]))
    if tags.comment and tags.comment.startswith("http"):
        id3["WOAR"] = WOAR(url=tags.comment.split("\n", 1)[0])
    if cover:
        id3.delall("APIC")
        id3.add(
            APIC(
                encoding=Encoding.LATIN1,
                mime=_cover_mime(cover),
                type=3,
                desc="Cover",
                data=cover,
            )
        )
    audio.save(v1=2, v2_version=3)
    return True


def _embed_mp4(path: Path, tags: TagPayload, cover: bytes | None) -> bool:
    from mutagen.mp4 import MP4, MP4Cover

    audio = MP4(path)
    if tags.title:
        audio["\xa9nam"] = [tags.title]
    if tags.artist:
        audio["\xa9ART"] = [tags.artist]
    if tags.album:
        audio["\xa9alb"] = [tags.album]
    if tags.album_artist:
        audio["aART"] = [tags.album_artist]
    if tags.year:
        audio["\xa9day"] = [tags.year]
    if tags.genre:
        audio["\xa9gen"] = [tags.genre]
    if tags.comment:
        audio["\xa9cmt"] = [tags.comment]
    if tags.lyrics:
        audio["\xa9lyr"] = [tags.lyrics]
    if tags.track:
        audio["trkn"] = [(tags.track, 0)]
    if cover:
        fmt = MP4Cover.FORMAT_PNG if _cover_mime(cover) == "image/png" else MP4Cover.FORMAT_JPEG
        audio["covr"] = [MP4Cover(cover, imageformat=fmt)]
    audio.save()
    return True


def _embed_vorbis(path: Path, tags: TagPayload, cover: bytes | None) -> bool:
    import base64

    from mutagen import File as MutagenFile
    from mutagen.flac import Picture

    audio = MutagenFile(path)
    if audio is None:
        return False
    mapping = {
        "title": tags.title,
        "artist": tags.artist,
        "album": tags.album,
        "albumartist": tags.album_artist,
        "date": tags.year,
        "genre": tags.genre,
        "lyrics": tags.lyrics,
        "comment": tags.comment,
    }
    for key, value in mapping.items():
        if value:
            audio[key] = value
    if tags.track:
        audio["tracknumber"] = str(tags.track)
    if cover:
        picture = Picture()
        picture.type = 3
        picture.mime = _cover_mime(cover)
        picture.desc = "Cover"
        picture.data = cover
        audio["metadata_block_picture"] = [base64.b64encode(picture.write()).decode("ascii")]
    audio.save()
    return True
