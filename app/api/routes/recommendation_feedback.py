from fastapi import APIRouter, Depends, Path, Response, status

from app.api.dependencies import get_recommendation_feedback_repository
from app.models.media import (
    MediaType,
    RecommendationFeedbackEntry,
    RecommendationFeedbackRecordRequest,
    RecommendationFeedbackSummary,
)
from app.repositories.recommendation_feedback import RecommendationFeedbackRepository

router = APIRouter(prefix="/api/v1/recommendation-feedback", tags=["recommendation-feedback"])


@router.get("", response_model=list[RecommendationFeedbackEntry])
def list_feedback(
    repository: RecommendationFeedbackRepository = Depends(get_recommendation_feedback_repository),
) -> list[RecommendationFeedbackEntry]:
    return repository.list()


@router.get("/summary", response_model=RecommendationFeedbackSummary)
def feedback_summary(
    repository: RecommendationFeedbackRepository = Depends(get_recommendation_feedback_repository),
) -> RecommendationFeedbackSummary:
    return repository.summary()


@router.post("/{media_type}/{tmdb_id}", response_model=RecommendationFeedbackEntry)
def record_feedback(
    payload: RecommendationFeedbackRecordRequest,
    media_type: MediaType,
    tmdb_id: int = Path(gt=0),
    repository: RecommendationFeedbackRepository = Depends(get_recommendation_feedback_repository),
) -> RecommendationFeedbackEntry:
    return repository.record(media_type, tmdb_id, payload.title, payload.action)


@router.delete(
    "/{media_type}/{tmdb_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_feedback(
    media_type: MediaType,
    tmdb_id: int = Path(gt=0),
    repository: RecommendationFeedbackRepository = Depends(get_recommendation_feedback_repository),
) -> Response:
    repository.remove(media_type, tmdb_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
