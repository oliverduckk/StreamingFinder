from fastapi.testclient import TestClient
import pytest

from app.api.dependencies import get_ratings_repository
from app.db.database import SQLiteDatabase
from app.main import app
from app.repositories.ratings import MediaRatingRepository
from app.services.rating_system import RATING_CATEGORIES, rating_total


def make_scores(value: float = 8.0) -> dict[str, float]:
    return {category.key: value for category in RATING_CATEGORIES}


def test_rating_total_uses_all_ten_categories() -> None:
    scores = make_scores(8.5)

    assert rating_total(scores) == 85.0


def test_rating_repository_persists_scores_and_notes(tmp_path) -> None:
    database_path = tmp_path / "ratings.db"
    first_repository = MediaRatingRepository(SQLiteDatabase(database_path))

    saved = first_repository.upsert(
        "movie",
        157336,
        make_scores(9.0),
        notes="Huge atmosphere and payoff.",
    )

    second_repository = MediaRatingRepository(SQLiteDatabase(database_path))
    loaded = second_repository.get("movie", 157336)

    assert saved.total == 90.0
    assert loaded is not None
    assert loaded.total == 90.0
    assert loaded.notes == "Huge atmosphere and payoff."
    assert len(loaded.categories) == 10
    assert loaded.categories[0].label == "Story"
    assert loaded.categories[-1].label == "Enjoyment"


def test_rating_repository_updates_and_deletes(tmp_path) -> None:
    repository = MediaRatingRepository(SQLiteDatabase(tmp_path / "ratings.db"))
    repository.upsert("tv", 1396, make_scores(7.0))

    updated = repository.upsert("tv", 1396, make_scores(9.5), notes="All timer.")

    assert updated.total == 95.0
    assert updated.notes == "All timer."
    assert repository.remove("tv", 1396) is True
    assert repository.get("tv", 1396) is None


def test_rating_repository_rejects_incomplete_score_sets(tmp_path) -> None:
    repository = MediaRatingRepository(SQLiteDatabase(tmp_path / "ratings.db"))

    with pytest.raises(ValueError):
        repository.upsert("movie", 157336, {"story": 9.0})


def test_rating_api_schema_and_crud(tmp_path) -> None:
    repository = MediaRatingRepository(SQLiteDatabase(tmp_path / "ratings.db"))
    app.dependency_overrides[get_ratings_repository] = lambda: repository

    try:
        client = TestClient(app)
        schema_response = client.get("/api/v1/ratings/schema")
        save_response = client.put(
            "/api/v1/ratings/movie/157336",
            json={
                "scores": make_scores(8.5),
                "notes": "Still hits.",
            },
        )
        get_response = client.get("/api/v1/ratings/movie/157336")
        list_response = client.get("/api/v1/ratings?media_type=movie")
        delete_response = client.delete("/api/v1/ratings/movie/157336")
        missing_response = client.get("/api/v1/ratings/movie/157336")

        assert schema_response.status_code == 200
        assert [item["label"] for item in schema_response.json()] == [
            "Story",
            "Characters",
            "Dialogue",
            "Visuals",
            "Soundtrack",
            "Worldbuilding",
            "Direction",
            "Pacing",
            "Emotional Impact",
            "Enjoyment",
        ]
        assert save_response.status_code == 200
        assert save_response.json()["total"] == 85.0
        assert get_response.json()["notes"] == "Still hits."
        assert len(list_response.json()) == 1
        assert delete_response.status_code == 204
        assert missing_response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_rating_api_rejects_non_half_point_scores(tmp_path) -> None:
    repository = MediaRatingRepository(SQLiteDatabase(tmp_path / "ratings.db"))
    app.dependency_overrides[get_ratings_repository] = lambda: repository
    scores = make_scores(8.0)
    scores["story"] = 8.3

    try:
        client = TestClient(app)
        response = client.put(
            "/api/v1/ratings/movie/157336",
            json={"scores": scores},
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
