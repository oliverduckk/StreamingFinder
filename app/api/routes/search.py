import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.clients.tmdb import TMDBClient
from app.core.config import Settings, get_settings
from app.models.media import MediaSearchResult

router = APIRouter(prefix="/api/v1", tags=["search"])


def get_tmdb_client(settings: Settings = Depends(get_settings)) -> TMDBClient:
    try:
        return TMDBClient(settings)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail="TMDB credentials are not configured.",
        ) from exc


@router.get("/search", response_model=list[MediaSearchResult])
async def search_media(
    query: str = Query(min_length=1, max_length=200),
    tmdb: TMDBClient = Depends(get_tmdb_client),
) -> list[MediaSearchResult]:
    try:
        return await tmdb.search_media(query.strip())
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail="TMDB returned an error while searching for media.",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="TMDB is currently unreachable.",
        ) from exc
