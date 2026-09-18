from collections.abc import Iterable
from typing import Literal

from app.models.media import LibraryStatus, MediaLibraryEntry, MediaRating, MediaType

LibrarySort = Literal["recent", "rating", "title", "year"]


def rating_totals(ratings: Iterable[MediaRating]) -> dict[tuple[MediaType, int], float]:
    """Return a lookup keyed by media identity for library presentation."""
    return {(rating.media_type, rating.tmdb_id): rating.total for rating in ratings}


def prepare_library_entries(
    entries: Iterable[MediaLibraryEntry],
    *,
    query: str = "",
    status: LibraryStatus | None = None,
    media_type: MediaType | None = None,
    favourite_only: bool = False,
    sort_by: LibrarySort = "recent",
    ratings: dict[tuple[MediaType, int], float] | None = None,
) -> list[MediaLibraryEntry]:
    """Filter and sort library entries for the desktop library view."""
    normalized_query = query.strip().casefold()
    filtered = [
        entry
        for entry in entries
        if (not normalized_query or normalized_query in entry.title.casefold())
        and (status is None or entry.status == status)
        and (media_type is None or entry.media_type == media_type)
        and (not favourite_only or entry.favourite)
    ]

    score_lookup = ratings or {}
    if sort_by == "rating":
        return sorted(
            filtered,
            key=lambda entry: (
                -score_lookup.get((entry.media_type, entry.tmdb_id), -1.0),
                entry.title.casefold(),
            ),
        )
    if sort_by == "title":
        return sorted(filtered, key=lambda entry: (entry.title.casefold(), entry.year or 0))
    if sort_by == "year":
        return sorted(
            filtered,
            key=lambda entry: (-(entry.year or 0), entry.title.casefold()),
        )
    if sort_by != "recent":
        raise ValueError(f"Unknown library sort: {sort_by}")

    return sorted(
        filtered,
        key=lambda entry: (entry.updated_at, entry.title.casefold()),
        reverse=True,
    )
