from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import (
    get_library_repository,
    get_media_metadata_service,
    get_ratings_repository,
)
from app.models.media import (
    MediaRating,
    MediaRatingSaveRequest,
    MediaType,
    MetadataTasteProfile,
    RatingCategoryDefinition,
    RatingsDashboard,
    TasteProfile,
)
from app.repositories.library import MediaLibraryRepository
from app.repositories.ratings import MediaRatingRepository
from app.services.media_metadata import MediaMetadataService
from app.services.metadata_taste import build_metadata_taste_profile
from app.services.rating_system import RATING_CATEGORIES
from app.services.ratings_dashboard import build_ratings_dashboard
from app.services.taste_profile import build_taste_profile

router = APIRouter(prefix="/api/v1/ratings", tags=["ratings"])


@router.get("/schema", response_model=list[RatingCategoryDefinition])
def get_rating_schema() -> list[RatingCategoryDefinition]:
    return [
        RatingCategoryDefinition(key=category.key, label=category.label, maximum=10.0)
        for category in RATING_CATEGORIES
    ]


@router.get("", response_model=list[MediaRating])
def list_ratings(
    media_type: MediaType | None = None,
    repository: MediaRatingRepository = Depends(get_ratings_repository),
) -> list[MediaRating]:
    return repository.list(media_type=media_type)


@router.get("/dashboard", response_model=RatingsDashboard)
def get_ratings_dashboard(
    ratings_repository: MediaRatingRepository = Depends(get_ratings_repository),
    library_repository: MediaLibraryRepository = Depends(get_library_repository),
) -> RatingsDashboard:
    return build_ratings_dashboard(
        ratings_repository.list(),
        library_repository.list(),
    )


@router.get("/taste-profile", response_model=TasteProfile)
def get_taste_profile(
    ratings_repository: MediaRatingRepository = Depends(get_ratings_repository),
    library_repository: MediaLibraryRepository = Depends(get_library_repository),
) -> TasteProfile:
    return build_taste_profile(
        ratings_repository.list(),
        library_repository.list(),
    )


@router.get("/metadata-profile", response_model=MetadataTasteProfile)
async def get_metadata_taste_profile(
    ratings_repository: MediaRatingRepository = Depends(get_ratings_repository),
    library_repository: MediaLibraryRepository = Depends(get_library_repository),
    metadata_service: MediaMetadataService = Depends(get_media_metadata_service),
) -> MetadataTasteProfile:
    ratings = ratings_repository.list()
    library_entries = library_repository.list()
    features = await metadata_service.get_many(
        [(rating.media_type, rating.tmdb_id) for rating in ratings]
    )
    return build_metadata_taste_profile(ratings, library_entries, features)


@router.get("/{media_type}/{tmdb_id}", response_model=MediaRating)
def get_rating(
    media_type: MediaType,
    tmdb_id: int,
    repository: MediaRatingRepository = Depends(get_ratings_repository),
) -> MediaRating:
    rating = repository.get(media_type, tmdb_id)
    if rating is None:
        raise HTTPException(status_code=404, detail="Rating not found.")
    return rating


@router.put("/{media_type}/{tmdb_id}", response_model=MediaRating)
def save_rating(
    media_type: MediaType,
    tmdb_id: int,
    request: MediaRatingSaveRequest,
    repository: MediaRatingRepository = Depends(get_ratings_repository),
) -> MediaRating:
    return repository.upsert(
        media_type,
        tmdb_id,
        request.scores,
        notes=request.notes,
    )


@router.delete("/{media_type}/{tmdb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rating(
    media_type: MediaType,
    tmdb_id: int,
    repository: MediaRatingRepository = Depends(get_ratings_repository),
) -> Response:
    if not repository.remove(media_type, tmdb_id):
        raise HTTPException(status_code=404, detail="Rating not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
