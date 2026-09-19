from app.models.media import (
    MediaFeatureProfile,
    MediaLibraryEntry,
    MediaRating,
    RatingCategoryScore,
)
from app.services.metadata_taste import build_metadata_taste_profile
from app.services.rating_system import RATING_CATEGORIES


def _rating(tmdb_id: int, title: str, score: float, enjoyment: float) -> MediaRating:
    categories = [
        RatingCategoryScore(
            key=category.key,
            label=category.label,
            score=enjoyment if category.key == "enjoyment" else score / 10.0,
        )
        for category in RATING_CATEGORIES
    ]
    return MediaRating(
        media_type="movie",
        tmdb_id=tmdb_id,
        title=title,
        year=2000,
        categories=categories,
        total=round(sum(item.score for item in categories), 1),
        notes=None,
        created_at="2026-01-01 00:00:00",
        updated_at="2026-01-01 00:00:00",
    )


def _entry(tmdb_id: int, title: str, favourite: bool = False) -> MediaLibraryEntry:
    return MediaLibraryEntry(
        media_type="movie",
        tmdb_id=tmdb_id,
        title=title,
        year=2000,
        status="watched",
        favourite=favourite,
        created_at="2026-01-01 00:00:00",
        updated_at="2026-01-01 00:00:00",
    )


def test_metadata_profile_separates_positive_and_negative_affinities() -> None:
    ratings = [
        _rating(1, "Crime One", 95, 10),
        _rating(2, "Crime Two", 90, 9.5),
        _rating(3, "Romance One", 45, 4.5),
        _rating(4, "Romance Two", 40, 4.0),
    ]
    library = [
        _entry(1, "Crime One", favourite=True),
        _entry(2, "Crime Two"),
        _entry(3, "Romance One"),
        _entry(4, "Romance Two"),
    ]
    features = {
        ("movie", 1): MediaFeatureProfile(
            media_type="movie",
            tmdb_id=1,
            genre_ids=[80],
            genre_names=["Crime"],
            keyword_ids=[10714],
            keyword_names=["serial killer"],
            creators=["David Fincher"],
        ),
        ("movie", 2): MediaFeatureProfile(
            media_type="movie",
            tmdb_id=2,
            genre_ids=[80],
            genre_names=["Crime"],
            keyword_ids=[10714],
            keyword_names=["serial killer"],
            creators=["David Fincher"],
        ),
        ("movie", 3): MediaFeatureProfile(
            media_type="movie",
            tmdb_id=3,
            genre_ids=[10749],
            genre_names=["Romance"],
            keyword_ids=[9673],
            keyword_names=["love story"],
            creators=["Other Director"],
        ),
        ("movie", 4): MediaFeatureProfile(
            media_type="movie",
            tmdb_id=4,
            genre_ids=[10749],
            genre_names=["Romance"],
            keyword_ids=[9673],
            keyword_names=["love story"],
            creators=["Other Director"],
        ),
    }

    profile = build_metadata_taste_profile(ratings, library, features)

    assert profile.metadata_coverage == 4
    assert profile.positive_genres[0].label == "Crime"
    assert profile.positive_genres[0].affinity > 0
    assert profile.negative_genres[0].label == "Romance"
    assert profile.negative_genres[0].affinity < 0
    assert profile.positive_keywords[0].label == "serial killer"
    assert profile.positive_creators[0].label == "David Fincher"
