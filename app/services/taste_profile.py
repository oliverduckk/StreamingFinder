from collections.abc import Iterable
from math import sqrt
from statistics import mean

from app.models.media import (
    MediaLibraryEntry,
    MediaRating,
    TasteAlignmentSignal,
    TasteCategorySignal,
    TasteProfile,
)
from app.services.rating_system import RATING_CATEGORIES


def build_taste_profile(
    ratings: Iterable[MediaRating],
    library_entries: Iterable[MediaLibraryEntry],
) -> TasteProfile:
    """Build deterministic taste signals from the user's structured ratings.

    This intentionally avoids pretending that a tiny history is a mature profile.
    Category averages describe what the user tends to score highly, while Pearson
    correlation against Enjoyment captures which category scores currently move
    most closely with enjoyment across rated titles.
    """
    rating_list = list(ratings)
    library_by_key = {
        (entry.media_type, entry.tmdb_id): entry for entry in library_entries
    }
    total_rated = len(rating_list)
    confidence = _confidence(total_rated)

    if not rating_list:
        return TasteProfile(
            total_rated=0,
            confidence="empty",
            average_total=None,
            score_spread=None,
            strongest_categories=[],
            enjoyment_alignments=[],
            favourite_average=None,
            non_favourite_average=None,
            favourite_delta=None,
            summary="Rate a few movies or shows and StreamingFinder will start mapping your taste.",
        )

    totals = [rating.total for rating in rating_list]
    category_averages = _category_averages(rating_list)
    trait_averages = {
        key: value for key, value in category_averages.items() if key != "enjoyment"
    }
    personal_category_mean = mean(trait_averages.values())
    labels = {category.key: category.label for category in RATING_CATEGORIES}

    strongest = sorted(
        (
            TasteCategorySignal(
                key=key,
                label=labels[key],
                average=round(value, 2),
                delta_from_personal_mean=round(value - personal_category_mean, 2),
            )
            for key, value in trait_averages.items()
        ),
        key=lambda item: (-item.average, item.label.casefold()),
    )[:3]

    enjoyment_alignments = _enjoyment_alignments(rating_list, labels)

    favourite_scores: list[float] = []
    non_favourite_scores: list[float] = []
    for rating in rating_list:
        entry = library_by_key.get((rating.media_type, rating.tmdb_id))
        if entry is not None and entry.favourite:
            favourite_scores.append(rating.total)
        else:
            non_favourite_scores.append(rating.total)

    favourite_average = round(mean(favourite_scores), 2) if favourite_scores else None
    non_favourite_average = (
        round(mean(non_favourite_scores), 2) if non_favourite_scores else None
    )
    favourite_delta = (
        round(favourite_average - non_favourite_average, 2)
        if favourite_average is not None and non_favourite_average is not None
        else None
    )

    return TasteProfile(
        total_rated=total_rated,
        confidence=confidence,
        average_total=round(mean(totals), 2),
        score_spread=round(max(totals) - min(totals), 2) if len(totals) > 1 else 0.0,
        strongest_categories=strongest,
        enjoyment_alignments=enjoyment_alignments,
        favourite_average=favourite_average,
        non_favourite_average=non_favourite_average,
        favourite_delta=favourite_delta,
        summary=_build_summary(
            total_rated=total_rated,
            confidence=confidence,
            strongest=strongest,
            alignments=enjoyment_alignments,
        ),
    )


def _category_averages(ratings: list[MediaRating]) -> dict[str, float]:
    values: dict[str, list[float]] = {category.key: [] for category in RATING_CATEGORIES}
    for rating in ratings:
        for score in rating.categories:
            if score.key in values:
                values[score.key].append(score.score)
    return {
        key: mean(scores)
        for key, scores in values.items()
        if scores
    }


def _enjoyment_alignments(
    ratings: list[MediaRating],
    labels: dict[str, str],
) -> list[TasteAlignmentSignal]:
    if len(ratings) < 3:
        return []

    score_maps = [
        {category.key: category.score for category in rating.categories}
        for rating in ratings
    ]
    enjoyment = [scores.get("enjoyment") for scores in score_maps]
    if any(value is None for value in enjoyment):
        return []
    enjoyment_values = [float(value) for value in enjoyment if value is not None]

    signals: list[TasteAlignmentSignal] = []
    for category in RATING_CATEGORIES:
        if category.key == "enjoyment":
            continue
        values = [scores.get(category.key) for scores in score_maps]
        if any(value is None for value in values):
            continue
        numeric_values = [float(value) for value in values if value is not None]
        correlation = _pearson(numeric_values, enjoyment_values)
        if correlation is None:
            continue
        signals.append(
            TasteAlignmentSignal(
                key=category.key,
                label=labels[category.key],
                correlation=round(correlation, 3),
                sample_size=len(numeric_values),
            )
        )

    return sorted(
        signals,
        key=lambda item: (-abs(item.correlation), -item.correlation, item.label.casefold()),
    )[:3]


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    x_mean = mean(xs)
    y_mean = mean(ys)
    x_delta = [value - x_mean for value in xs]
    y_delta = [value - y_mean for value in ys]
    denominator = sqrt(
        sum(value * value for value in x_delta)
        * sum(value * value for value in y_delta)
    )
    if denominator == 0:
        return None
    return sum(x * y for x, y in zip(x_delta, y_delta, strict=True)) / denominator


def _confidence(total_rated: int) -> str:
    if total_rated == 0:
        return "empty"
    if total_rated < 5:
        return "early"
    if total_rated < 15:
        return "developing"
    return "established"


def _build_summary(
    *,
    total_rated: int,
    confidence: str,
    strongest: list[TasteCategorySignal],
    alignments: list[TasteAlignmentSignal],
) -> str:
    if not strongest:
        return "Rate a few movies or shows and StreamingFinder will start mapping your taste."

    standout_text = ", ".join(item.label for item in strongest[:3])
    if total_rated < 3:
        return (
            f"Early profile: your highest-scoring categories are {standout_text}. "
            "Rate at least 3 varied titles before enjoyment-alignment signals become meaningful."
        )

    if alignments:
        alignment_text = ", ".join(item.label for item in alignments[:2])
        prefix = "Developing profile" if confidence != "established" else "Established profile"
        return (
            f"{prefix}: you currently score {standout_text} highest. "
            f"Across your ratings, {alignment_text} move most closely with Enjoyment."
        )

    return (
        f"Your highest-scoring categories are {standout_text}. "
        "Add more varied ratings to reveal which categories track most closely with Enjoyment."
    )
