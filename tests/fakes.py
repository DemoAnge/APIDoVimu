from pathlib import Path

from app.core.exceptions import ExtractionError
from app.services.jobs import Job

FAKE_VIDEO_INFO = {
    "id": "dQw4w9WgXcQ",
    "title": "Never Gonna Give You Up",
    "extractor": "youtube",
    "extractor_key": "Youtube",
    "duration": 213,
    "uploader": "RickAstleyVEVO",
    "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "description": "Rick Astley",
    "formats": [
        {
            "format_id": "18",
            "ext": "mp4",
            "height": 360,
            "width": 640,
            "fps": 30,
            "vcodec": "avc1.42001E",
            "acodec": "mp4a.40.2",
            "filesize": 12_000_000,
            "tbr": 500,
            "abr": 96,
        },
        {
            "format_id": "136",
            "ext": "mp4",
            "height": 720,
            "width": 1280,
            "fps": 30,
            "vcodec": "avc1.4d401f",
            "acodec": "none",
            "filesize": 40_000_000,
            "tbr": 1500,
        },
        {
            "format_id": "137",
            "ext": "mp4",
            "height": 1080,
            "width": 1920,
            "fps": 30,
            "vcodec": "avc1.640028",
            "acodec": "none",
            "filesize": 80_000_000,
            "tbr": 3000,
        },
        {
            "format_id": "140",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "abr": 128,
            "filesize": 3_400_000,
        },
        {
            "format_id": "251",
            "ext": "webm",
            "vcodec": "none",
            "acodec": "opus",
            "abr": 160,
            "filesize": 4_000_000,
        },
    ],
}

FAKE_PLAYLIST_INFO = {
    "_type": "playlist",
    "id": "PLtest",
    "title": "Favoritos",
    "extractor": "youtube:tab",
    "extractor_key": "YoutubeTab",
    "webpage_url": "https://www.youtube.com/playlist?list=PLtest",
    "entries": [
        {
            "id": "aaa",
            "title": "Tema 1",
            "url": "https://www.youtube.com/watch?v=aaa",
            "duration": 120,
            "uploader": "Canal",
            "thumbnail": "https://i.ytimg.com/vi/aaa/hqdefault.jpg",
        },
        {
            "id": "bbb",
            "title": "Tema 2",
            "url": "https://www.youtube.com/watch?v=bbb",
            "duration": 90,
        },
    ],
}

FAKE_SEARCH_INFO = {
    "_type": "playlist",
    "entries": [
        {
            "id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "duration": 213,
            "uploader": "RickAstleyVEVO",
            "thumbnails": [{"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg", "width": 480, "height": 360}],
        }
    ],
}


class FakeExtractor:
    def __init__(self, info=None, search_info=None, error=None):
        self.info = FAKE_VIDEO_INFO if info is None else info
        self.search_info = search_info
        self.error = error

    def inspect(self, url: str, playlist: bool = False) -> dict:
        if self.error:
            raise self.error
        if playlist and self.info.get("_type") != "playlist":
            return FAKE_PLAYLIST_INFO
        return self.info

    def search(self, query: str, limit: int = 10) -> dict:
        if self.error:
            raise self.error
        return self.search_info or FAKE_SEARCH_INFO


class FailingExtractor(FakeExtractor):
    def __init__(self):
        super().__init__(error=ExtractionError("No se pudo extraer información de este enlace."))


class FakeDownloader:
    def download(self, job: Job, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / "clip.mp4"
        path.write_bytes(b"fake-media-bytes")
        return path
