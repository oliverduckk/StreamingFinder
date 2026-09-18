from app.models.media import MediaLibraryEntry, MediaRating, RatingCategoryScore
from app.services.library_catalog import prepare_library_entries, rating_totals


def entry(
    title: str,
    tmdb_id: int,
    *,
    media_type: str = "movie",
    status: str = "watched",
    favourite: bool = False,
    year: int | None = 2000,
    updated_at: str = "2026-01-01 00:00:00",
) -> MediaLibraryEntry:
    return MediaLibraryEntry(
        media_type=media_type,
        tmdb_id=tmdb_id,
        title=title,
        year=year,
        overview=None,
        poster_path=None,
        status=status,
        favourite=favourite,
        created_at="2026-01-01 00:00:00",
        updated_at=updated_at,
    )


def rating(title: str, tmdb_id: int, total: float) -> MediaRating:
    return MediaRating(
        media_type="movie",
        tmdb_id=tmdb_id,
        title=title,
        year=2000,
        categories=[RatingCategoryScore(key="story", label="Story", score=10.0)],
        total=total,
        notes=None,
        created_at="2026-01-01 00:00:00",
        updated_at="2026-01-01 00:00:00",
    )


def test_filters_library_by_query_status_type_and_favourite() -> None:
    entries = [
        entry("Alien", 1, favourite=True),
        entry("Alien: Earth", 2, media_type="tv", status="watching", favourite=True),
        entry("Arrival", 3, status="watchlist"),
    ]

    results = prepare_library_entries(
        entries,
        query="alien",
        status="watched",
        media_type="movie",
        favourite_only=True,
    )

    assert [item.tmdb_id for item in results] == [1]


def test_recent_sort_uses_latest_updated_first() -> None:
    entries = [
        entry("Older", 1, updated_at="2026-01-01 00:00:00"),
        entry("Newer", 2, updated_at="2026-02-01 00:00:00"),
    ]

    results = prepare_library_entries(entries, sort_by="recent")

    assert [item.title for item in results] == ["Newer", "Older"]


def test_rating_sort_places_highest_rated_first_and_unrated_last() -> None:
    entries = [entry("B", 2), entry("Unrated", 3), entry("A", 1)]
    totals = {("movie", 1): 91.5, ("movie", 2): 98.5}

    results = prepare_library_entries(entries, sort_by="rating", ratings=totals)

    assert [item.title for item in results] == ["B", "A", "Unrated"]


def test_title_and_year_sorting() -> None:
    entries = [
        entry("Zulu", 1, year=1999),
        entry("Alien", 2, year=1979),
        entry("Arrival", 3, year=2016),
    ]

    assert [item.title for item in prepare_library_entries(entries, sort_by="title")] == [
        "Alien",
        "Arrival",
        "Zulu",
    ]
    assert [item.title for item in prepare_library_entries(entries, sort_by="year")] == [
        "Arrival",
        "Zulu",
        "Alien",
    ]


def test_rating_totals_builds_media_identity_lookup() -> None:
    totals = rating_totals([rating("Alien", 1, 96.0), rating("Arrival", 2, 91.5)])

    assert totals == {("movie", 1): 96.0, ("movie", 2): 91.5}
