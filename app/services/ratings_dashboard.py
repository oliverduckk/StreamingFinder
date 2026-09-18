from collections.abc import Iterable
from statistics import mean

from app.models.media import (
    MediaLibraryEntry,
    MediaRating,
    RatedTitleSummary,
    RatingCategoryAverage,
    RatingsDashboard,
)
from app.services.rating_system import RATING_CATEGORIES


def build_ratings_dashboard(
    ratings: Iterable[MediaRating],
    library_entries: Iterable[MediaLibraryEntry],
) -> RatingsDashboard:
    """Aggregate personal rating data for the desktop dashboard and API."""
    rating_list = list(ratings)
    library_by_key = {
        (entry.media_type, entry.tmdb_id): entry for entry in library_entries
    }

    category_averages: list[RatingCategoryAverage] = []
    for category in RATING_CATEGORIES:
        scores = [
            score.score
            for rating in rating_list
            for score in rating.categories
            if score.key == category.key
        ]
        category_averages.append(
            RatingCategoryAverage(
                key=category.key,
                label=category.label,
                average=round(mean(scores), 2) if scores else None,
            )
        )

    summaries = [
        _summary_for_rating(rating, library_by_key.get((rating.media_type, rating.tmdb_id)))
        for rating in rating_list
    ]
    top_rated = sorted(
        summaries,
        key=lambda item: (-item.total, item.title.casefold(), item.year or 0),
    )[:6]
    recent_rated = sorted(
        summaries,
        key=lambda item: (item.updated_at, item.title.casefold()),
        reverse=True,
    )[:6]

    movie_scores = [rating.total for rating in rating_list if rating.media_type == "movie"]
    tv_scores = [rating.total for rating in rating_list if rating.media_type == "tv"]
    totals = [rating.total for rating in rating_list]

    return RatingsDashboard(
        total_rated=len(rating_list),
        average_total=round(mean(totals), 2) if totals else None,
        highest_total=max(totals) if totals else None,
        movie_average=round(mean(movie_scores), 2) if movie_scores else None,
        tv_average=round(mean(tv_scores), 2) if tv_scores else None,
        category_averages=category_averages,
        top_rated=top_rated,
        recent_rated=recent_rated,
    )


def _summary_for_rating(
    rating: MediaRating,
    library_entry: MediaLibraryEntry | None,
) -> RatedTitleSummary:
    title = rating.title or (library_entry.title if library_entry is not None else "Unknown title")
    year = rating.year if rating.year is not None else (
        library_entry.year if library_entry is not None else None
    )
    poster_path = library_entry.poster_path if library_entry is not None else None
    favourite = bool(library_entry and library_entry.favourite)
    return RatedTitleSummary(
        media_type=rating.media_type,
        tmdb_id=rating.tmdb_id,
        title=title,
        year=year,
        poster_path=poster_path,
        total=rating.total,
        favourite=favourite,
        updated_at=rating.updated_at,
    )
