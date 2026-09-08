from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.api.deps import get_jobs, get_settings, verify_api_key
from app.config import Settings
from app.core.exceptions import JobNotFoundError, JobNotReadyError
from app.models.schemas import JobResponse, JobStatus
from app.services.jobs import JobStore

router = APIRouter(
    prefix="/api/v1/jobs",
    tags=["jobs"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("", response_model=list[JobResponse])
def list_jobs(jobs: JobStore = Depends(get_jobs)) -> list[JobResponse]:
    return [job.to_response() for job in jobs.list_recent()]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, jobs: JobStore = Depends(get_jobs)) -> JobResponse:
    job = jobs.get(job_id)
    if job is None:
        raise JobNotFoundError("No existe esa descarga.")
    return job.to_response()


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request, jobs: JobStore = Depends(get_jobs)):
    if jobs.get(job_id) is None:
        raise JobNotFoundError("No existe esa descarga.")

    async def generate():
        terminal = {JobStatus.ready, JobStatus.failed, JobStatus.cancelled}
        while True:
            if await request.is_disconnected():
                break
            job = jobs.get(job_id)
            if job is None:
                break
            payload = job.to_response().model_dump(mode="json")
            yield f"data: {json.dumps(payload)}\n\n"
            if job.status in terminal:
                break
            await asyncio.sleep(0.4)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/{job_id}/file")
def download_file(job_id: str, jobs: JobStore = Depends(get_jobs)) -> FileResponse:
    job = jobs.get(job_id)
    if job is None:
        raise JobNotFoundError("No existe esa descarga.")
    if job.status != JobStatus.ready or job.filepath is None:
        raise JobNotReadyError("La descarga todavía no está lista.")
    path = Path(job.filepath)
    if not path.is_file():
        raise JobNotReadyError("El archivo ya no está disponible.")
    return FileResponse(
        path=path,
        filename=job.filename or path.name,
        media_type=job.mime or "application/octet-stream",
        content_disposition_type="attachment",
    )


@router.delete("/{job_id}", status_code=204)
def cancel_job(
    job_id: str,
    jobs: JobStore = Depends(get_jobs),
    settings: Settings = Depends(get_settings),
) -> None:
    job = jobs.get(job_id)
    if job is None:
        raise JobNotFoundError("No existe esa descarga.")
    jobs.cancel(job_id)
    if job.status in {JobStatus.queued, JobStatus.ready, JobStatus.failed, JobStatus.cancelled}:
        jobs.update(job_id, status=JobStatus.cancelled)
        dest = settings.download_dir / job_id
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
