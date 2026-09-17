from fastapi import Depends, HTTPException

from app.clients.tmdb import TMDBClient
from app.core.config import Settings, get_settings
from app.db.database import SQLiteDatabase
from app.repositories.preferences import StreamingPreferencesRepository


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
