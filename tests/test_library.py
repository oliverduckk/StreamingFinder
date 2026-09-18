from fastapi.testclient import TestClient

from app.api.dependencies import get_library_repository
from app.db.database import SQLiteDatabase
from app.main import app
from app.models.media import MediaSearchResult
from app.repositories.library import MediaLibraryRepository


def make_interstellar() -> MediaSearchResult:
    return MediaSearchResult(
        tmdb_id=157336,
        media_type="movie",
        title="Interstellar",
        year=2014,
        overview="Explorers travel through a wormhole in space.",
        poster_path="/poster.jpg",
    )


def test_library_persists_status_and_favourite(tmp_path) -> None:
    database_path = tmp_path / "library.db"
    first_repository = MediaLibraryRepository(SQLiteDatabase(database_path))

    first_repository.upsert(make_interstellar(), "watchlist")
    first_repository.set_favourite("movie", 157336, True)

    second_repository = MediaLibraryRepository(SQLiteDatabase(database_path))
    saved = second_repository.get("movie", 157336)

    assert saved is not None
    assert saved.title == "Interstellar"
    assert saved.status == "watchlist"
    assert saved.favourite is True


def test_library_upsert_preserves_favourite_when_status_changes(tmp_path) -> None:
    repository = MediaLibraryRepository(SQLiteDatabase(tmp_path / "library.db"))
    media = make_interstellar()

    repository.upsert(media, "watchlist", favourite=True)
    updated = repository.upsert(media, "watched")

    assert updated.status == "watched"
    assert updated.favourite is True


def test_library_can_filter_and_remove_items(tmp_path) -> None:
    repository = MediaLibraryRepository(SQLiteDatabase(tmp_path / "library.db"))
    repository.upsert(make_interstellar(), "watched", favourite=True)
    repository.upsert(
        MediaSearchResult(
            tmdb_id=1396,
            media_type="tv",
            title="Breaking Bad",
            year=2008,
        ),
        "watchlist",
    )

    favourites = repository.list(favourite=True)
    watched = repository.list(status="watched")

    assert [item.title for item in favourites] == ["Interstellar"]
    assert [item.title for item in watched] == ["Interstellar"]
    assert repository.remove("movie", 157336) is True
    assert repository.get("movie", 157336) is None


def test_library_api_can_save_read_list_and_delete(tmp_path) -> None:
    repository = MediaLibraryRepository(SQLiteDatabase(tmp_path / "library.db"))
    app.dependency_overrides[get_library_repository] = lambda: repository

    try:
        client = TestClient(app)
        save_response = client.put(
            "/api/v1/library/movie/157336",
            json={
                "title": "Interstellar",
                "year": 2014,
                "overview": "Explorers travel through a wormhole in space.",
                "poster_path": "/poster.jpg",
                "status": "watched",
                "favourite": True,
            },
        )
        get_response = client.get("/api/v1/library/movie/157336")
        list_response = client.get("/api/v1/library?status=watched&favourite=true")
        delete_response = client.delete("/api/v1/library/movie/157336")
        missing_response = client.get("/api/v1/library/movie/157336")

        assert save_response.status_code == 200
        assert save_response.json()["status"] == "watched"
        assert save_response.json()["favourite"] is True
        assert get_response.status_code == 200
        assert [item["title"] for item in list_response.json()] == ["Interstellar"]
        assert delete_response.status_code == 204
        assert missing_response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_library_persists_anime_classification(tmp_path) -> None:
    repository = MediaLibraryRepository(SQLiteDatabase(tmp_path / "library.db"))
    anime = MediaSearchResult(
        tmdb_id=16498,
        media_type="tv",
        title="Attack on Titan",
        year=2013,
        genre_ids=[16, 18],
        original_language="ja",
        is_anime=True,
    )

    repository.upsert(anime, "watched")
    saved = repository.get("tv", 16498)

    assert saved is not None
    assert saved.is_anime is True
