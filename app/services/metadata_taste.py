from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean

from app.models.media import (
    MediaFeatureProfile,
    MediaLibraryEntry,
    MediaRating,
    MetadataAffinitySignal,
    MetadataTasteProfile,
)


@dataclass(slots=True)
class _Evidence:
    label: str
    values: list[float] = field(default_factory=list)
    positive: int = 0
    negative: int = 0
    supporting_titles: list[tuple[float, str]] = field(default_factory=list)


def build_metadata_taste_profile(
    ratings: list[MediaRating],
    library_entries: list[MediaLibraryEntry],
    features_by_key: dict[tuple[str, int], MediaFeatureProfile],
) -> MetadataTasteProfile:
    """Build interpretable genre/keyword/creator affinities from the full rating history."""
    library_by_key = {
        (entry.media_type, entry.tmdb_id): entry for entry in library_entries
    }
    usable = [
        rating
        for rating in ratings
        if (rating.media_type, rating.tmdb_id) in features_by_key
    ]
    total_rated = len(ratings)
    coverage = len(usable)
    confidence = _confidence(coverage)

    if not usable:
        return MetadataTasteProfile(
            total_rated=total_rated,
            metadata_coverage=0,
            confidence="empty",
            summary=(
                "StreamingFinder has not cached enough TMDB metadata yet to build "
                "genre, keyword and creator affinities."
            ),
        )

    average_total = mean(rating.total for rating in usable)
    average_enjoyment = mean(_enjoyment(rating) for rating in usable)

    genres: dict[str, _Evidence] = {}
    keywords: dict[str, _Evidence] = {}
    creators: dict[str, _Evidence] = {}

    for rating in usable:
        key = (rating.media_type, rating.tmdb_id)
        feature = features_by_key[key]
        entry = library_by_key.get(key)
        title = entry.title if entry is not None else (rating.title or f"TMDB {rating.tmdb_id}")
        weight = rating_preference_weight(
            rating,
            average_total=average_total,
            average_enjoyment=average_enjoyment,
            favourite=bool(entry and entry.favourite),
            dropped=bool(entry and entry.status == "dropped"),
        )

        for genre_id, genre_name in zip(feature.genre_ids, feature.genre_names, strict=False):
            _add_evidence(genres, str(genre_id), genre_name, weight, title)
        for keyword_id, keyword_name in zip(
            feature.keyword_ids,
            feature.keyword_names,
            strict=False,
        ):
            _add_evidence(keywords, str(keyword_id), keyword_name, weight, title)
        for creator in feature.creators:
            _add_evidence(creators, creator.casefold(), creator, weight, title)

    positive_genres, negative_genres = _rank_affinities(
        "genre",
        genres,
        total_samples=coverage,
        minimum_samples=2,
        limit=6,
        prevalence_penalty=0.55,
    )
    positive_keywords, negative_keywords = _rank_affinities(
        "keyword",
        keywords,
        total_samples=coverage,
        minimum_samples=2,
        limit=6,
        prevalence_penalty=0.35,
    )
    positive_creators, negative_creators = _rank_affinities(
        "creator",
        creators,
        total_samples=coverage,
        minimum_samples=2,
        limit=5,
        prevalence_penalty=0.0,
    )

    return MetadataTasteProfile(
        total_rated=total_rated,
        metadata_coverage=coverage,
        confidence=confidence,
        positive_genres=positive_genres,
        negative_genres=negative_genres,
        positive_keywords=positive_keywords,
        negative_keywords=negative_keywords,
        positive_creators=positive_creators,
        negative_creators=negative_creators,
        summary=_summary(
            coverage,
            total_rated,
            positive_genres,
            positive_keywords,
            positive_creators,
        ),
    )


def rating_preference_weight(
    rating: MediaRating,
    *,
    average_total: float,
    average_enjoyment: float,
    favourite: bool = False,
    dropped: bool = False,
) -> float:
    """Continuous -1..1 preference signal centred on this user's own averages."""
    total_delta = (rating.total - average_total) / 30.0
    enjoyment_delta = (_enjoyment(rating) - average_enjoyment) / 3.0
    signal = 0.62 * total_delta + 0.38 * enjoyment_delta
    if favourite:
        signal += 0.18
    if dropped:
        signal -= 0.18
    return max(-1.0, min(1.0, signal))


def build_weighted_feature_inputs(
    ratings: list[MediaRating],
    library_entries: list[MediaLibraryEntry],
    features_by_key: dict[tuple[str, int], MediaFeatureProfile],
) -> list[tuple[float, MediaFeatureProfile]]:
    """Return continuous metadata weights for use by the recommendation engine."""
    library_by_key = {
        (entry.media_type, entry.tmdb_id): entry for entry in library_entries
    }
    usable = [
        rating
        for rating in ratings
        if (rating.media_type, rating.tmdb_id) in features_by_key
    ]
    if not usable:
        return []

    average_total = mean(rating.total for rating in usable)
    average_enjoyment = mean(_enjoyment(rating) for rating in usable)
    weighted: list[tuple[float, MediaFeatureProfile]] = []
    for rating in usable:
        key = (rating.media_type, rating.tmdb_id)
        entry = library_by_key.get(key)
        weight = rating_preference_weight(
            rating,
            average_total=average_total,
            average_enjoyment=average_enjoyment,
            favourite=bool(entry and entry.favourite),
            dropped=bool(entry and entry.status == "dropped"),
        )
        if abs(weight) < 0.025:
            continue
        weighted.append((weight, features_by_key[key]))
    return weighted


def _add_evidence(
    target: dict[str, _Evidence],
    key: str,
    label: str,
    weight: float,
    title: str,
) -> None:
    evidence = target.setdefault(key, _Evidence(label=label))
    evidence.values.append(weight)
    if weight >= 0.12:
        evidence.positive += 1
    elif weight <= -0.12:
        evidence.negative += 1
    if abs(weight) >= 0.12:
        evidence.supporting_titles.append((abs(weight), title))


def _rank_affinities(
    kind: str,
    evidence_by_key: dict[str, _Evidence],
    *,
    total_samples: int,
    minimum_samples: int,
    limit: int,
    prevalence_penalty: float,
) -> tuple[list[MetadataAffinitySignal], list[MetadataAffinitySignal]]:
    signals: list[MetadataAffinitySignal] = []
    for key, evidence in evidence_by_key.items():
        sample_size = len(evidence.values)
        if sample_size < minimum_samples:
            continue
        raw = mean(evidence.values)
        reliability = sample_size / (sample_size + (1.5 if kind == "creator" else 2.0))
        prevalence = sample_size / max(1, total_samples)
        specificity = max(0.35, 1.0 - prevalence_penalty * prevalence)
        affinity = max(-1.0, min(1.0, raw * reliability * specificity))
        if abs(affinity) < 0.035:
            continue
        supporting_titles = [
            title
            for _, title in sorted(
                evidence.supporting_titles,
                key=lambda item: (-item[0], item[1].casefold()),
            )[:3]
        ]
        signals.append(
            MetadataAffinitySignal(
                kind=kind,
                key=key,
                label=evidence.label,
                affinity=round(affinity, 3),
                sample_size=sample_size,
                positive_evidence=evidence.positive,
                negative_evidence=evidence.negative,
                supporting_titles=supporting_titles,
            )
        )

    positive = sorted(
        (item for item in signals if item.affinity > 0),
        key=lambda item: (-item.affinity, -item.sample_size, item.label.casefold()),
    )[:limit]
    negative = sorted(
        (item for item in signals if item.affinity < 0),
        key=lambda item: (item.affinity, -item.sample_size, item.label.casefold()),
    )[:limit]
    return positive, negative


def _confidence(coverage: int) -> str:
    if coverage == 0:
        return "empty"
    if coverage < 8:
        return "early"
    if coverage < 25:
        return "developing"
    return "established"


def _summary(
    coverage: int,
    total_rated: int,
    genres: list[MetadataAffinitySignal],
    keywords: list[MetadataAffinitySignal],
    creators: list[MetadataAffinitySignal],
) -> str:
    bits: list[str] = []
    if genres:
        bits.append("genres: " + ", ".join(item.label for item in genres[:3]))
    if keywords:
        bits.append("themes: " + ", ".join(item.label for item in keywords[:3]))
    if creators:
        bits.append("creators: " + ", ".join(item.label for item in creators[:2]))
    if not bits:
        return (
            f"Metadata cached for {coverage} of {total_rated} rated titles. "
            "Add more varied ratings before strong metadata affinities emerge."
        )
    return (
        f"Metadata cached for {coverage} of {total_rated} rated titles. "
        "Your strongest current signals are " + "; ".join(bits) + "."
    )


def _enjoyment(rating: MediaRating) -> float:
    return next(
        (score.score for score in rating.categories if score.key == "enjoyment"),
        rating.total / 10.0,
    )
