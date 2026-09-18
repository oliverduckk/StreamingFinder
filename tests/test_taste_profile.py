from fastapi.testclient import TestClient

from app.api.dependencies import get_library_repository, get_ratings_repository
from app.db.database import SQLiteDatabase
from app.main import app
from app.models.media import MediaLibraryEntry, MediaRating, RatingCategoryScore
from app.repositories.library import MediaLibraryRepository
from app.repositories.ratings import MediaRatingRepository
from app.services.rating_system import RATING_CATEGORIES
from app.services.taste_profile import build_taste_profile


def make_rating(
    tmdb_id: int,
    *,
    enjoyment: float,
    story: float,
    visuals: float,
    default: float = 8.0,
) -> MediaRating:
    values = {
        category.key: default
        for category in RATING_CATEGORIES
    }
    values["story"] = story
    values["visuals"] = visuals
    values["enjoyment"] = enjoyment
    categories = [
        RatingCategoryScore(key=category.key, label=category.label, score=values[category.key])
        for category in RATING_CATEGORIES
    ]
    return MediaRating(
        media_type="movie",
        tmdb_id=tmdb_id,
        title=f"Movie {tmdb_id}",
        year=2000 + tmdb_id,
        categories=categories,
        total=sum(score.score for score in categories),
        notes=None,
        created_at="2026-09-18 10:00:00",
        updated_at="2026-09-18 10:00:00",
    )


def make_library_entry(tmdb_id: int, *, favourite: bool) -> MediaLibraryEntry:
    return MediaLibraryEntry(
        media_type="movie",
        tmdb_id=tmdb_id,
        title=f"Movie {tmdb_id}",
        year=2000 + tmdb_id,
        overview=None,
        poster_path=None,
        status="watched",
        favourite=favourite,
        created_at="2026-09-18 10:00:00",
        updated_at="2026-09-18 10:00:00",
    )


def test_taste_profile_empty_state() -> None:
    profile = build_taste_profile([], [])

    assert profile.total_rated == 0
    assert profile.confidence == "empty"
    assert profile.strongest_categories == []
    assert profile.enjoyment_alignments == []
    assert "Rate a few" in profile.summary


def test_taste_profile_marks_small_samples_as_early() -> None:
    profile = build_taste_profile(
        [
            make_rating(1, enjoyment=9.0, story=9.5, visuals=10.0),
            make_rating(2, enjoyment=8.0, story=8.5, visuals=9.5),
        ],
        [],
    )

    assert profile.confidence == "early"
    assert profile.total_rated == 2
    assert profile.enjoyment_alignments == []
    assert len(profile.strongest_categories) == 3
    assert profile.strongest_categories[0].key == "visuals"
    assert "at least 3" in profile.summary


def test_taste_profile_finds_enjoyment_alignment_and_favourite_delta() -> None:
    ratings = [
        make_rating(1, enjoyment=5.0, story=5.0, visuals=10.0),
        make_rating(2, enjoyment=6.0, story=6.0, visuals=9.0),
        make_rating(3, enjoyment=8.0, story=8.0, visuals=7.0),
        make_rating(4, enjoyment=10.0, story=10.0, visuals=5.0),
        make_rating(5, enjoyment=9.0, story=9.0, visuals=6.0),
    ]
    library = [
        make_library_entry(1, favourite=False),
        make_library_entry(2, favourite=False),
        make_library_entry(3, favourite=False),
        make_library_entry(4, favourite=True),
        make_library_entry(5, favourite=True),
    ]

    profile = build_taste_profile(ratings, library)

    assert profile.confidence == "developing"
    assert profile.enjoyment_alignments[0].key in {"story", "visuals"}
    correlations = {item.key: item.correlation for item in profile.enjoyment_alignments}
    assert correlations["story"] == 1.0
    assert correlations["visuals"] == -1.0
    assert profile.favourite_average is not None
    assert profile.non_favourite_average is not None
    assert profile.favourite_delta is not None
    assert profile.favourite_delta > 0


def test_taste_profile_established_after_fifteen_ratings() -> None:
    ratings = [
        make_rating(
            index,
            enjoyment=float(5 + (index % 6)),
            story=float(5 + (index % 6)),
            visuals=float(10 - (index % 6)),
        )
        for index in range(1, 16)
    ]

    profile = build_taste_profile(ratings, [])

    assert profile.confidence == "established"
    assert profile.total_rated == 15


def test_taste_profile_api(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "taste.db")
    library_repository = MediaLibraryRepository(database)
    ratings_repository = MediaRatingRepository(database)

    from app.models.media import MediaSearchResult

    for tmdb_id, favourite, score in [
        (1, False, 7.0),
        (2, False, 8.0),
        (3, True, 9.5),
    ]:
        library_repository.upsert(
            MediaSearchResult(
                media_type="movie",
                tmdb_id=tmdb_id,
                title=f"Movie {tmdb_id}",
                year=2000 + tmdb_id,
                overview=None,
                poster_path=None,
            ),
            "watched",
            favourite=favourite,
        )
        scores = {category.key: score for category in RATING_CATEGORIES}
        scores["story"] = score
        scores["enjoyment"] = score
        ratings_repository.upsert("movie", tmdb_id, scores)

    app.dependency_overrides[get_ratings_repository] = lambda: ratings_repository
    app.dependency_overrides[get_library_repository] = lambda: library_repository

    try:
        response = TestClient(app).get("/api/v1/ratings/taste-profile")
        payload = response.json()

        assert response.status_code == 200
        assert payload["total_rated"] == 3
        assert payload["confidence"] == "early"
        assert payload["strongest_categories"]
        assert payload["favourite_delta"] is not None
    finally:
        app.dependency_overrides.clear()
