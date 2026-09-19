from pathlib import Path

from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_library_repository,
    get_media_metadata_service,
    get_ratings_repository,
)
from app.db.database import SQLiteDatabase
from app.main import app
from app.models.media import MediaFeatureProfile, MediaSearchResult
from app.repositories.library import MediaLibraryRepository
from app.repositories.ratings import MediaRatingRepository
from app.services.rating_system import RATING_CATEGORIES


class FakeMetadataService:
    async def get_many(self, keys, *, concurrency=6):
        result = {}
        for media_type, tmdb_id in keys:
            positive = tmdb_id in {1, 2}
            result[(media_type, tmdb_id)] = MediaFeatureProfile(
                media_type=media_type,
                tmdb_id=tmdb_id,
                genre_ids=[80 if positive else 10749],
                genre_names=["Crime" if positive else "Romance"],
                keyword_ids=[1 if positive else 2],
                keyword_names=["investigation" if positive else "love story"],
                creators=["Test Creator" if positive else "Other Creator"],
            )
        return result


def test_metadata_profile_endpoint_returns_structured_affinities(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "metadata-api.db")
    library = MediaLibraryRepository(database)
    ratings = MediaRatingRepository(database)
    for tmdb_id, value in [(1, 9.5), (2, 8.5), (3, 4.0)]:
        media = MediaSearchResult(
            tmdb_id=tmdb_id,
            media_type="movie",
            title=f"Title {tmdb_id}",
        )
        library.upsert(media, "watched", favourite=tmdb_id == 1)
        ratings.upsert(
            "movie",
            tmdb_id,
            {category.key: value for category in RATING_CATEGORIES},
        )

    app.dependency_overrides[get_library_repository] = lambda: library
    app.dependency_overrides[get_ratings_repository] = lambda: ratings
    app.dependency_overrides[get_media_metadata_service] = lambda: FakeMetadataService()
    try:
        response = TestClient(app).get("/api/v1/ratings/metadata-profile")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata_coverage"] == 3
    assert payload["total_rated"] == 3
    assert payload["positive_genres"][0]["label"] == "Crime"
