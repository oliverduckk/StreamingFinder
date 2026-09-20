from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_assistant_service
from app.models.assistant import (
    AssistantProfileResponse,
    AssistantTitleContextResponse,
    AssistantWhereToWatchResponse,
)
from app.models.media import MediaType, RecommendationResponse
from app.services.assistant import AssistantService

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


@router.get("/where-to-watch", response_model=AssistantWhereToWatchResponse)
async def where_to_watch(
    query: str = Query(min_length=1, max_length=200),
    media_type: MediaType | None = Query(default=None),
    year: int | None = Query(default=None, ge=1870, le=2100),
    only_my_services: bool = Query(default=True),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantWhereToWatchResponse:
    try:
        return await service.where_to_watch(
            query,
            media_type=media_type,
            year=year,
            only_my_services=only_my_services,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="TMDB returned an error.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="TMDB is currently unreachable.") from exc


@router.get("/title-context", response_model=AssistantTitleContextResponse)
async def title_context(
    query: str = Query(min_length=1, max_length=200),
    media_type: MediaType | None = Query(default=None),
    year: int | None = Query(default=None, ge=1870, le=2100),
    include_availability: bool = Query(default=False),
    only_my_services: bool = Query(default=True),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantTitleContextResponse:
    try:
        return await service.title_context(
            query,
            media_type=media_type,
            year=year,
            include_availability=include_availability,
            only_my_services=only_my_services,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="TMDB returned an error.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="TMDB is currently unreachable.") from exc


@router.get("/recommendations", response_model=RecommendationResponse)
async def assistant_recommendations(
    media_type: Literal[
        "all", "movie", "tv", "anime", "anime_movie", "anime_tv"
    ] = Query(default="all"),
    limit: int = Query(default=5, ge=1, le=12),
    only_my_services: bool = Query(default=True),
    discovery_mode: Literal["familiar", "balanced", "hidden"] = Query(default="familiar"),
    service: AssistantService = Depends(get_assistant_service),
) -> RecommendationResponse:
    return await service.recommend(
        media_type=media_type,
        limit=limit,
        only_my_services=only_my_services,
        discovery_mode=discovery_mode,
    )


@router.get("/profile", response_model=AssistantProfileResponse)
def assistant_profile(
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantProfileResponse:
    return service.profile()
