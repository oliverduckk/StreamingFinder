from fastapi import Depends, HTTPException

from app.clients.tmdb import TMDBClient
from app.core.config import Settings, get_settings
from app.db.database import SQLiteDatabase
from app.repositories.dismissals import RecommendationDismissalRepository
from app.repositories.library import MediaLibraryRepository
from app.repositories.preferences import StreamingPreferencesRepository
from app.repositories.ratings import MediaRatingRepository
from app.services.recommendations import RecommendationService


def get_tmdb_client(settings: Settings = Depends(get_settings)) -> TMDBClient:
    try:
        return TMDBClient(settings)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail="TMDB credentials are not configured.",
        ) from exc


def get_preferences_repository(
    settings: Settings = Depends(get_settings),
) -> StreamingPreferencesRepository:
    return StreamingPreferencesRepository(SQLiteDatabase(settings.database_path))


def get_library_repository(
    settings: Settings = Depends(get_settings),
) -> MediaLibraryRepository:
    return MediaLibraryRepository(SQLiteDatabase(settings.database_path))


def get_ratings_repository(
    settings: Settings = Depends(get_settings),
) -> MediaRatingRepository:
    return MediaRatingRepository(SQLiteDatabase(settings.database_path))


def get_dismissals_repository(
    settings: Settings = Depends(get_settings),
) -> RecommendationDismissalRepository:
    return RecommendationDismissalRepository(SQLiteDatabase(settings.database_path))


def get_recommendation_service(
    tmdb: TMDBClient = Depends(get_tmdb_client),
    library: MediaLibraryRepository = Depends(get_library_repository),
    ratings: MediaRatingRepository = Depends(get_ratings_repository),
    preferences: StreamingPreferencesRepository = Depends(get_preferences_repository),
    dismissals: RecommendationDismissalRepository = Depends(get_dismissals_repository),
) -> RecommendationService:
    return RecommendationService(tmdb, library, ratings, preferences, dismissals)
