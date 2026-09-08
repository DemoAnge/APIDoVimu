from fastapi import APIRouter, Request

from app import __version__
from app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
@router.get("/api/v1/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        version=__version__,
        ffmpeg=bool(request.app.state.ffmpeg_available),
        max_concurrent_downloads=settings.max_concurrent_downloads,
    )
