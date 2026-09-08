from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    downloading = "downloading"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    cancelled = "cancelled"


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class InspectRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048, examples=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])
    playlist: bool = False


class QualityOption(BaseModel):
    id: str = Field(..., examples=["video:720", "audio:mp3:192"])
    kind: str
    label: str
    ext: str
    height: int | None = None
    width: int | None = None
    fps: float | None = None
    abr: int | None = None
    filesize_bytes: int | None = None
    filesize_label: str | None = None
    note: str | None = None
    needs_ffmpeg: bool = False
    recommended: bool = False


class TrackMetadata(BaseModel):
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    track: int | None = None
    genre: str | None = None
    year: str | None = None
    lyrics: str | None = None
    comment: str | None = None
    thumbnail: str | None = None
    duration_seconds: int | None = None
    width: int | None = None
    height: int | None = None
    embedded: bool = False


class PlaylistEntry(BaseModel):
    media_id: str
    title: str
    url: str | None = None
    duration: int | None = None
    duration_label: str | None = None
    thumbnail: str | None = None
    uploader: str | None = None


class InspectResponse(BaseModel):
    source: str
    extractor: str
    media_id: str
    title: str
    uploader: str | None = None
    duration: int | None = None
    duration_label: str | None = None
    thumbnail: str | None = None
    webpage_url: str
    description: str | None = None
    is_playlist: bool = False
    entries: list[PlaylistEntry] = Field(default_factory=list)
    video: list[QualityOption] = Field(default_factory=list)
    audio: list[QualityOption] = Field(default_factory=list)
    ffmpeg_available: bool = False
    metadata: TrackMetadata | None = None


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    quality_id: str = Field(..., min_length=3, max_length=64, examples=["video:720", "audio:mp3:192", "audio:best"])


class JobCreatedResponse(BaseModel):
    job_id: str
    status: JobStatus
    poll_url: str
    events_url: str
    file_url: str


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: float
    speed_bytes: float | None = None
    eta_seconds: int | None = None
    title: str | None = None
    filename: str | None = None
    mime: str | None = None
    filesize_bytes: int | None = None
    quality_id: str
    download_url: str | None = None
    error: str | None = None
    metadata: TrackMetadata | None = None


class SearchResult(BaseModel):
    media_id: str
    title: str
    url: str | None = None
    duration: int | None = None
    duration_label: str | None = None
    thumbnail: str | None = None
    uploader: str | None = None
    source: str = "youtube"


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class HealthResponse(BaseModel):
    status: str
    version: str
    ffmpeg: bool
    max_concurrent_downloads: int
