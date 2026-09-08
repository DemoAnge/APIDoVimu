from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.models.schemas import JobResponse, JobStatus, TrackMetadata


@dataclass
class Job:
    id: str
    url: str
    quality_id: str
    status: JobStatus = JobStatus.queued
    progress: float = 0.0
    speed_bytes: float | None = None
    eta_seconds: int | None = None
    title: str | None = None
    filename: str | None = None
    filepath: Path | None = None
    mime: str | None = None
    filesize_bytes: int | None = None
    error: str | None = None
    metadata: TrackMetadata | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancelled: bool = False

    def to_response(self) -> JobResponse:
        download_url = None
        if self.status == JobStatus.ready:
            download_url = f"/api/v1/jobs/{self.id}/file"
        return JobResponse(
            job_id=self.id,
            status=self.status,
            progress=round(self.progress, 1),
            speed_bytes=self.speed_bytes,
            eta_seconds=self.eta_seconds,
            title=self.title,
            filename=self.filename,
            mime=self.mime,
            filesize_bytes=self.filesize_bytes,
            quality_id=self.quality_id,
            download_url=download_url,
            error=self.error,
            metadata=self.metadata,
        )


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, url: str, quality_id: str) -> Job:
        job = Job(id=str(uuid.uuid4()), url=url, quality_id=quality_id)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_recent(self, limit: int = 50) -> list[Job]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def update(self, job_id: str, **fields) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for key, value in fields.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.updated_at = time.time()
            return job

    def cancel(self, job_id: str) -> Job | None:
        return self.update(job_id, cancelled=True)

    def pop(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.pop(job_id, None)

    def expired(self, ttl_seconds: int) -> list[Job]:
        now = time.time()
        with self._lock:
            return [job for job in self._jobs.values() if now - job.updated_at > ttl_seconds]
