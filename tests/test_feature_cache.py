from pathlib import Path

import pytest

from app.db.database import SQLiteDatabase
from app.models.media import MediaFeatureProfile
from app.repositories.features import MediaFeatureRepository
from app.services.media_metadata import MediaMetadataService


def _profile() -> MediaFeatureProfile:
    return MediaFeatureProfile(
        media_type="movie",
        tmdb_id=550,
        genre_ids=[18, 53],
        genre_names=["Drama", "Thriller"],
        keyword_ids=[825, 3392],
        keyword_names=["support group", "identity"],
        collection_id=None,
        collection_name=None,
        creators=["David Fincher"],
        original_language="en",
        is_anime=False,
    )


def test_feature_repository_round_trips_metadata(tmp_path: Path) -> None:
    repository = MediaFeatureRepository(SQLiteDatabase(tmp_path / "features.db"))
    repository.upsert(_profile())

    loaded = repository.get("movie", 550)

    assert loaded == _profile()


class FakeTMDB:
    def __init__(self) -> None:
        self.calls = 0

    async def get_media_features(self, media_type: str, tmdb_id: int):
        self.calls += 1
        return _profile()


@pytest.mark.anyio
async def test_metadata_service_reuses_sqlite_cache(tmp_path: Path) -> None:
    repository = MediaFeatureRepository(SQLiteDatabase(tmp_path / "features.db"))
    tmdb = FakeTMDB()
    service = MediaMetadataService(tmdb, repository)

    first = await service.get("movie", 550)
    second = await service.get("movie", 550)
    fresh_service = MediaMetadataService(tmdb, repository)
    third = await fresh_service.get("movie", 550)

    assert first == second == third
    assert tmdb.calls == 1
