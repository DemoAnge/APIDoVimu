import asyncio

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_extractor, verify_api_key
from app.models.schemas import SearchResponse
from app.services.extractor import MediaExtractor
from app.services.normalize import normalize_search

router = APIRouter(
    prefix="/api/v1/search",
    tags=["search"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("", response_model=SearchResponse)
async def search_media(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=20),
    extractor: MediaExtractor = Depends(get_extractor),
) -> SearchResponse:
    info = await asyncio.to_thread(extractor.search, q.strip(), limit)
    return SearchResponse(query=q.strip(), results=normalize_search(info, q.strip()))
