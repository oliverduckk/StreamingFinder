from collections.abc import Iterable
from typing import Literal

from app.models.media import LibraryStatus, MediaLibraryEntry, MediaRating, MediaType

LibrarySort = Literal["recent", "rating", "title", "year"]
LibraryContentFilter = Literal["all", "movie", "tv", "anime"]


def rating_totals(ratings: Iterable[MediaRating]) -> dict[tuple[MediaType, int], float]:
    """Return a lookup keyed by media identity for library presentation."""
    return {(rating.media_type, rating.tmdb_id): rating.total for rating in ratings}


def prepare_library_entries(
    entries: Iterable[MediaLibraryEntry],
    *,
    query: str = "",
    status: LibraryStatus | None = None,
    media_type: MediaType | None = None,
    content_filter: LibraryContentFilter = "all",
    favourite_only: bool = False,
    sort_by: LibrarySort = "recent",
    descending: bool | None = None,
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
        and _matches_content_filter(entry, content_filter)
        and (not favourite_only or entry.favourite)
    ]

    # Preserve existing defaults when older callers do not specify direction.
    if descending is None:
        descending = sort_by != "title"

    score_lookup = ratings or {}
    if sort_by == "rating":
        # Unrated items always appear last, regardless of sort direction.
        rated = [
            item for item in filtered if (item.media_type, item.tmdb_id) in score_lookup
        ]
        unrated = [
            item for item in filtered if (item.media_type, item.tmdb_id) not in score_lookup
        ]
        rated.sort(key=lambda item: item.title.casefold())
        rated.sort(
            key=lambda item: score_lookup[(item.media_type, item.tmdb_id)],
            reverse=descending,
        )
        return rated + sorted(unrated, key=lambda item: item.title.casefold())
    if sort_by == "title":
        return sorted(
            filtered, key=lambda item: (item.title.casefold(), item.year or 0),
            reverse=descending,
        )
    if sort_by == "year":
        # Titles with unknown release dates should not appear before dated entries.
        dated = [item for item in filtered if item.year is not None]
        undated = [item for item in filtered if item.year is None]
        dated.sort(key=lambda item: item.title.casefold())
        dated.sort(key=lambda item: item.year, reverse=descending)
        return dated + sorted(undated, key=lambda item: item.title.casefold())
    if sort_by != "recent":
        raise ValueError(f"Unknown library sort: {sort_by}")

    filtered.sort(key=lambda item: item.title.casefold())
    filtered.sort(key=lambda item: item.updated_at, reverse=descending)
    return filtered


def _matches_content_filter(
    entry: MediaLibraryEntry,
    content_filter: LibraryContentFilter,
) -> bool:
    if content_filter == "all":
        return True
    if content_filter == "anime":
        return entry.is_anime is True
    if content_filter == "movie":
        return entry.media_type == "movie" and entry.is_anime is not True
    if content_filter == "tv":
        return entry.media_type == "tv" and entry.is_anime is not True
    raise ValueError(f"Unknown library content filter: {content_filter}")
