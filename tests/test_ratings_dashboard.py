from fastapi.testclient import TestClient

from app.api.dependencies import get_library_repository, get_ratings_repository
from app.db.database import SQLiteDatabase
from app.main import app
from app.models.media import (
    MediaLibraryEntry,
    MediaRating,
    RatingCategoryScore,
)
from app.repositories.library import MediaLibraryRepository
from app.repositories.ratings import MediaRatingRepository
from app.services.rating_system import RATING_CATEGORIES
from app.services.ratings_dashboard import build_ratings_dashboard


def make_rating(
    media_type: str,
    tmdb_id: int,
    title: str,
    default_score: float,
    *,
    story_score: float | None = None,
    updated_at: str = "2026-09-18 10:00:00",
) -> MediaRating:
    categories = [
        RatingCategoryScore(
            key=category.key,
            label=category.label,
            score=(
                story_score
                if category.key == "story" and story_score is not None
                else default_score
            ),
        )
        for category in RATING_CATEGORIES
    ]
    return MediaRating(
        media_type=media_type,
        tmdb_id=tmdb_id,
        title=title,
        year=2000 + tmdb_id,
        categories=categories,
        total=sum(item.score for item in categories),
        notes=None,
        created_at=updated_at,
        updated_at=updated_at,
    )


def make_library_entry(
    media_type: str,
    tmdb_id: int,
    title: str,
    *,
    favourite: bool = False,
) -> MediaLibraryEntry:
    return MediaLibraryEntry(
        media_type=media_type,
        tmdb_id=tmdb_id,
        title=title,
        year=2000 + tmdb_id,
        overview=None,
        poster_path=f"/{tmdb_id}.jpg",
        status="watched",
        favourite=favourite,
        created_at="2026-09-18 09:00:00",
        updated_at="2026-09-18 09:00:00",
    )


def test_dashboard_empty_state() -> None:
    dashboard = build_ratings_dashboard([], [])

    assert dashboard.total_rated == 0
    assert dashboard.average_total is None
    assert dashboard.highest_total is None
    assert dashboard.movie_average is None
    assert dashboard.tv_average is None
    assert len(dashboard.category_averages) == 10
    assert all(item.average is None for item in dashboard.category_averages)
    assert dashboard.top_rated == []
    assert dashboard.recent_rated == []


def test_dashboard_aggregates_totals_categories_and_media_types() -> None:
    movie = make_rating("movie", 1, "Movie One", 8.0, story_score=10.0)
    show = make_rating("tv", 2, "Show Two", 6.0, story_score=8.0)
    entries = [
        make_library_entry("movie", 1, "Movie One", favourite=True),
        make_library_entry("tv", 2, "Show Two"),
    ]

    dashboard = build_ratings_dashboard([movie, show], entries)

    assert dashboard.total_rated == 2
    assert dashboard.average_total == 72.0
    assert dashboard.highest_total == 82.0
    assert dashboard.movie_average == 82.0
    assert dashboard.tv_average == 62.0
    assert dashboard.category_averages[0].label == "Story"
    assert dashboard.category_averages[0].average == 9.0
    assert dashboard.category_averages[1].average == 7.0
    assert dashboard.top_rated[0].title == "Movie One"
    assert dashboard.top_rated[0].favourite is True
    assert dashboard.top_rated[0].poster_path == "/1.jpg"


def test_dashboard_orders_top_and_recent_ratings() -> None:
    ratings = [
        make_rating("movie", 1, "Alpha", 7.0, updated_at="2026-09-16 10:00:00"),
        make_rating("movie", 2, "Beta", 9.0, updated_at="2026-09-17 10:00:00"),
        make_rating("tv", 3, "Gamma", 8.0, updated_at="2026-09-18 10:00:00"),
    ]

    dashboard = build_ratings_dashboard(ratings, [])

    assert [item.title for item in dashboard.top_rated] == ["Beta", "Gamma", "Alpha"]
    assert [item.title for item in dashboard.recent_rated] == ["Gamma", "Beta", "Alpha"]


def test_ratings_dashboard_api(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "dashboard.db")
    library_repository = MediaLibraryRepository(database)
    ratings_repository = MediaRatingRepository(database)

    from app.models.media import MediaSearchResult

    library_repository.upsert(
        MediaSearchResult(
            media_type="movie",
            tmdb_id=157336,
            title="Interstellar",
            year=2014,
            overview="Space.",
            poster_path="/interstellar.jpg",
        ),
        "watched",
        favourite=True,
    )
    ratings_repository.upsert(
        "movie",
        157336,
        {category.key: 9.0 for category in RATING_CATEGORIES},
        notes="Huge.",
    )

    app.dependency_overrides[get_ratings_repository] = lambda: ratings_repository
    app.dependency_overrides[get_library_repository] = lambda: library_repository

    try:
        response = TestClient(app).get("/api/v1/ratings/dashboard")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_rated"] == 1
        assert payload["average_total"] == 90.0
        assert payload["movie_average"] == 90.0
        assert payload["tv_average"] is None
        assert payload["top_rated"][0]["title"] == "Interstellar"
        assert payload["top_rated"][0]["favourite"] is True
        assert payload["category_averages"][0] == {
            "key": "story",
            "label": "Story",
            "average": 9.0,
        }
    finally:
        app.dependency_overrides.clear()
