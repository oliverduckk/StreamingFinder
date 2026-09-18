from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_recommendation_service
from app.models.media import RecommendationResponse
from app.services.recommendations import RecommendationService

router = APIRouter(prefix="/api/v1", tags=["recommendations"])


@router.get("/recommendations", response_model=RecommendationResponse)
async def get_recommendations(
    media_type: Literal["all", "movie", "tv", "anime"] = Query(default="all"),
    limit: int = Query(default=12, ge=1, le=24),
    only_my_services: bool = Query(default=True),
    discovery_mode: Literal["familiar", "balanced", "hidden"] = Query(default="balanced"),
    service: RecommendationService = Depends(get_recommendation_service),
) -> RecommendationResponse:
    return await service.recommend(
        media_type=media_type,
        limit=limit,
        only_my_services=only_my_services,
        discovery_mode=discovery_mode,
    )
