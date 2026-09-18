from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from dataclasses import dataclass, field
from math import log10
from typing import Literal

from app.clients.tmdb import TMDBClient
from app.models.media import (
    MediaFeatureProfile,
    MediaLibraryEntry,
    MediaRating,
    MediaSearchResult,
    RecommendationCandidate,
    RecommendationItem,
    RecommendationResponse,
)
from app.repositories.dismissals import RecommendationDismissalRepository
from app.repositories.library import MediaLibraryRepository
from app.repositories.preferences import StreamingPreferencesRepository
from app.repositories.ratings import MediaRatingRepository

RecommendationMediaFilter = Literal["all", "movie", "tv", "anime"]
RecommendationDiscoveryMode = Literal["familiar", "balanced", "hidden"]
ANIMATION_GENRE_ID = 16


@dataclass(frozen=True, slots=True)
class RecommendationSeed:
    media_type: Literal["movie", "tv"]
    tmdb_id: int
    title: str
    total: float
    favourite: bool
    enjoyment: float
    weight: float


@dataclass(frozen=True, slots=True)
class NegativeSignal:
    media_type: Literal["movie", "tv"]
    tmdb_id: int
    title: str
    total: float
    enjoyment: float
    weight: float


@dataclass(slots=True)
class CandidateAccumulator:
    media: RecommendationCandidate
    vote_average: float
    vote_count: int
    popularity: float
    seeds: dict[tuple[str, int], RecommendationSeed] = field(default_factory=dict)
    discovered: bool = False


@dataclass(slots=True)
class FeatureTasteModel:
    genre_weights: dict[int, float] = field(default_factory=dict)
    genre_names: dict[int, str] = field(default_factory=dict)
    genre_prevalence: dict[int, float] = field(default_factory=dict)
    keyword_weights: dict[int, float] = field(default_factory=dict)
    keyword_names: dict[int, str] = field(default_factory=dict)
    keyword_prevalence: dict[int, float] = field(default_factory=dict)
    creator_weights: dict[str, float] = field(default_factory=dict)

    def top_positive_genres(self, limit: int = 4) -> list[int]:
        scored = [
            (
                value * max(0.3, 1.0 - 0.7 * self.genre_prevalence.get(key, 0.0)),
                key,
            )
            for key, value in self.genre_weights.items()
            if value > 0.12
        ]
        return [
            key
            for _, key in sorted(
                scored,
                key=lambda item: (-item[0], self.genre_names.get(item[1], "").casefold()),
            )
        ][:limit]


class RecommendationService:
    """Build deterministic recommendations from ratings, metadata and availability.

    Positive titles generate candidates. Positive and negative ratings then shape
    a local feature profile from genres, keywords and creators. The final list is
    diversified so a single franchise or genre cannot monopolise the page.
    """

    def __init__(
        self,
        tmdb: TMDBClient,
        library: MediaLibraryRepository,
        ratings: MediaRatingRepository,
        preferences: StreamingPreferencesRepository,
        dismissals: RecommendationDismissalRepository | None = None,
    ) -> None:
        self.tmdb = tmdb
        self.library = library
        self.ratings = ratings
        self.preferences = preferences
        self.dismissals = dismissals
        self._feature_cache: dict[tuple[str, int], MediaFeatureProfile] = {}

    async def recommend(
        self,
        *,
        media_type: RecommendationMediaFilter = "all",
        limit: int = 12,
        only_my_services: bool = True,
        discovery_mode: RecommendationDiscoveryMode = "balanced",
    ) -> RecommendationResponse:
        limit = max(1, min(int(limit), 24))
        ratings = self.ratings.list()
        library_entries = self.library.list()

        # TV and anime share TMDB's "tv" media type, so pull a broader signal
        # pool first, classify it using TMDB metadata, then build a subtype-specific
        # taste model. This stops a large anime library from hijacking live-action TV.
        signal_media_type: RecommendationMediaFilter = (
            "all" if media_type == "anime" else media_type
        )
        signal_pool = 24 if media_type in {"tv", "anime"} else 12
        raw_seeds = select_recommendation_seeds(
            ratings,
            library_entries,
            media_type=signal_media_type,
            limit=signal_pool,
        )
        raw_negatives = select_negative_signals(
            ratings,
            library_entries,
            media_type=signal_media_type,
            limit=16 if media_type in {"tv", "anime"} else 8,
        )

        if not raw_seeds:
            return RecommendationResponse(
                media_filter=media_type,
                discovery_mode=discovery_mode,
                only_my_services=only_my_services,
                generated_from=0,
                total_considered=0,
                message="Rate a few titles you genuinely like before generating recommendations.",
                items=[],
            )

        feature_inputs: list[RecommendationSeed | NegativeSignal] = [
            *raw_seeds,
            *raw_negatives,
        ]
        feature_results = await asyncio.gather(
            *(self._get_features(item.media_type, item.tmdb_id) for item in feature_inputs),
            return_exceptions=True,
        )
        weighted_features: list[tuple[float, MediaFeatureProfile]] = []
        features_for_signals: dict[tuple[str, int], MediaFeatureProfile] = {}
        seeds: list[RecommendationSeed] = []
        negatives: list[NegativeSignal] = []
        for signal, result in zip(feature_inputs, feature_results, strict=True):
            if isinstance(result, Exception):
                # Movie/all recommendations can still use a seed if one metadata
                # request fails. TV/anime need metadata for subtype classification.
                if media_type in {"all", "movie"} and isinstance(signal, RecommendationSeed):
                    seeds.append(signal)
                continue
            if not _feature_matches_filter(result, media_type):
                continue
            features_for_signals[(signal.media_type, signal.tmdb_id)] = result
            weight = signal.weight if isinstance(signal, RecommendationSeed) else -signal.weight
            weighted_features.append((weight, result))
            if isinstance(signal, RecommendationSeed):
                seeds.append(signal)
            else:
                negatives.append(signal)

        seeds = seeds[:10]
        negatives = negatives[:8]
        if not seeds:
            subtype = "live-action TV" if media_type == "tv" else "anime"
            return RecommendationResponse(
                media_filter=media_type,
                discovery_mode=discovery_mode,
                only_my_services=only_my_services,
                generated_from=0,
                total_considered=0,
                message=f"Rate a few {subtype} titles you genuinely like first.",
                items=[],
            )

        # Rebuild the weighted model from the signals that survived subtype filtering.
        allowed_keys = {
            (item.media_type, item.tmdb_id) for item in [*seeds, *negatives]
        }
        weighted_features = [
            (weight, feature)
            for weight, feature in weighted_features
            if (feature.media_type, feature.tmdb_id) in allowed_keys
        ]
        taste_model = build_feature_taste_model(weighted_features)
        active_seeds = diversify_recommendation_seeds(
            seeds,
            features_for_signals,
            limit=min(8, len(seeds)),
        )

        candidate_batches = await asyncio.gather(
            *(
                self.tmdb.get_related_media(seed.media_type, seed.tmdb_id)
                for seed in active_seeds
            ),
            return_exceptions=True,
        )

        candidates: dict[tuple[str, int], CandidateAccumulator] = {}
        for seed, batch in zip(active_seeds, candidate_batches, strict=True):
            if isinstance(batch, Exception):
                continue
            for candidate in batch:
                if not _candidate_matches_filter(candidate, media_type):
                    continue
                accumulator = _accumulate_candidate(candidates, candidate)
                accumulator.seeds[(seed.media_type, seed.tmdb_id)] = seed

        discover_types: list[Literal["movie", "tv"]]
        if media_type in {"all", "anime"}:
            discover_types = ["movie", "tv"]
        else:
            discover_types = [media_type]
        if hasattr(self.tmdb, "discover_media"):
            discovery_requests = [
                (
                    kind,
                    top_positive_genres_for_media(
                        weighted_features,
                        kind,
                        limit=4,
                    ),
                )
                for kind in discover_types
            ]
            discovery_requests = [
                (kind, genres)
                for kind, genres in discovery_requests
                if genres
            ]
            discovery_jobs = []
            for kind, genres in discovery_requests:
                kwargs: dict[str, object] = {
                    "sort_by": (
                        "popularity.desc"
                        if discovery_mode == "familiar"
                        else "vote_average.desc"
                    )
                }
                if media_type == "anime":
                    kwargs.update(
                        original_language="ja",
                        required_genre_id=ANIMATION_GENRE_ID,
                        minimum_vote_count={
                            "familiar": 250,
                            "balanced": 50,
                            "hidden": 15,
                        }[discovery_mode],
                    )
                elif kind == "tv":
                    if media_type == "tv":
                        kwargs["excluded_genre_ids"] = [ANIMATION_GENRE_ID]
                    kwargs["minimum_vote_count"] = {
                        "familiar": 1000,
                        "balanced": 300,
                        "hidden": 40,
                    }[discovery_mode]
                elif kind == "movie":
                    kwargs["minimum_vote_count"] = {
                        "familiar": 1000,
                        "balanced": 350,
                        "hidden": 50,
                    }[discovery_mode]
                discovery_jobs.append(self.tmdb.discover_media(kind, genres, **kwargs))

            discovered_batches = await asyncio.gather(
                *discovery_jobs,
                return_exceptions=True,
            )
            for batch in discovered_batches:
                if isinstance(batch, Exception):
                    continue
                for candidate in batch:
                    if not _candidate_matches_filter(candidate, media_type):
                        continue
                    accumulator = _accumulate_candidate(candidates, candidate)
                    accumulator.discovered = True

        library_by_key = {
            (entry.media_type, entry.tmdb_id): entry for entry in library_entries
        }
        dismissed_keys = (
            {(item.media_type, item.tmdb_id) for item in self.dismissals.list()}
            if self.dismissals is not None
            else set()
        )

        preliminary = rank_candidates(
            candidates,
            library_by_key,
            taste_model=taste_model,
            dismissed_keys=dismissed_keys,
            media_filter=media_type,
            discovery_mode=discovery_mode,
        )
        total_considered = len(preliminary)

        # Enrich only the strongest candidates. Metadata is cached for the life
        # of the app, so repeated recommendation runs become substantially faster.
        enrichment_pool = preliminary[: min(max(limit * 2, 18), 24)]
        enrichment_results = await asyncio.gather(
            *(
                self._get_features(item.media_type, item.tmdb_id)
                for item in enrichment_pool
            ),
            return_exceptions=True,
        )
        features_by_key: dict[tuple[str, int], MediaFeatureProfile] = {}
        for item, result in zip(enrichment_pool, enrichment_results, strict=True):
            if isinstance(result, Exception):
                continue
            features_by_key[(item.media_type, item.tmdb_id)] = result

        ranked = rank_candidates(
            candidates,
            library_by_key,
            taste_model=taste_model,
            features_by_key=features_by_key,
            dismissed_keys=dismissed_keys,
            media_filter=media_type,
            discovery_mode=discovery_mode,
        )
        pool_limit = min(max(limit * 2, 18), 24)
        pool = diversify_recommendations(ranked, limit=pool_limit)

        enabled_services = set(self.preferences.get_enabled_services())
        if only_my_services and not enabled_services:
            return RecommendationResponse(
                media_filter=media_type,
                discovery_mode=discovery_mode,
                only_my_services=True,
                generated_from=len(active_seeds),
                total_considered=total_considered,
                message=(
                    "No streaming services are selected. Enable a service in Search, "
                    "or turn off the availability filter."
                ),
                items=[],
            )

        items: list[RecommendationItem] = []
        if only_my_services:
            semaphore = asyncio.Semaphore(6)

            async def add_availability(item: RecommendationItem) -> RecommendationItem:
                async with semaphore:
                    providers = await self.tmdb.get_subscription_providers(
                        item.media_type,
                        item.tmdb_id,
                        service_keys=enabled_services,
                    )
                item.providers = providers
                if providers:
                    item.reasons.append(_availability_reason(providers))
                return item

            results = await asyncio.gather(
                *(add_availability(item) for item in pool),
                return_exceptions=True,
            )
            available = [
                result
                for result in results
                if isinstance(result, RecommendationItem) and result.providers
            ]
            items = diversify_recommendations(available, limit=limit)
        else:
            items = diversify_recommendations(pool, limit=limit)

        message = _response_message(
            count=len(items),
            only_my_services=only_my_services,
            generated_from=len(active_seeds),
        )
        return RecommendationResponse(
            media_filter=media_type,
            discovery_mode=discovery_mode,
            only_my_services=only_my_services,
            generated_from=len(active_seeds),
            total_considered=total_considered,
            message=message,
            items=items,
        )

    async def _get_features(
        self,
        media_type: Literal["movie", "tv"],
        tmdb_id: int,
    ) -> MediaFeatureProfile:
        key = (media_type, tmdb_id)
        cached = self._feature_cache.get(key)
        if cached is not None:
            return cached
        result = await self.tmdb.get_media_features(media_type, tmdb_id)
        self._feature_cache[key] = result
        return result


def select_recommendation_seeds(
    ratings: list[MediaRating],
    library_entries: list[MediaLibraryEntry],
    *,
    media_type: RecommendationMediaFilter = "all",
    limit: int = 12,
) -> list[RecommendationSeed]:
    library_by_key = {
        (entry.media_type, entry.tmdb_id): entry for entry in library_entries
    }
    seeds: list[RecommendationSeed] = []

    for rating in ratings:
        if media_type != "all" and rating.media_type != media_type:
            continue
        entry = library_by_key.get((rating.media_type, rating.tmdb_id))
        if entry is None:
            continue
        enjoyment = _enjoyment(rating)
        favourite = bool(entry.favourite)

        if rating.total < 70.0 and enjoyment < 7.0 and not favourite:
            continue

        quality = max(0.0, min(1.0, (rating.total - 55.0) / 45.0))
        enjoyment_component = max(0.0, min(1.0, enjoyment / 10.0))
        weight = 0.62 * quality + 0.38 * enjoyment_component
        if favourite:
            weight += 0.18

        seeds.append(
            RecommendationSeed(
                media_type=rating.media_type,
                tmdb_id=rating.tmdb_id,
                title=entry.title,
                total=rating.total,
                favourite=favourite,
                enjoyment=enjoyment,
                weight=weight,
            )
        )

    return sorted(
        seeds,
        key=lambda seed: (
            -int(seed.favourite),
            -seed.weight,
            -seed.total,
            seed.title.casefold(),
        ),
    )[: max(1, limit)]


def diversify_recommendation_seeds(
    seeds: list[RecommendationSeed],
    features_by_key: dict[tuple[str, int], MediaFeatureProfile],
    *,
    limit: int,
) -> list[RecommendationSeed]:
    """Avoid letting several entries from one franchise dominate candidate generation."""
    if limit <= 0:
        return []
    selected: list[RecommendationSeed] = []
    deferred: list[RecommendationSeed] = []
    seen_franchises: set[str] = set()

    for seed in seeds:
        feature = features_by_key.get((seed.media_type, seed.tmdb_id))
        franchise_key = None
        if feature is not None and feature.collection_id is not None:
            franchise_key = f"collection:{feature.collection_id}"
        elif ":" in seed.title:
            prefix = seed.title.casefold().split(":", 1)[0].strip()
            if len(prefix) >= 4:
                franchise_key = "title:" + re.sub(r"[^a-z0-9]+", " ", prefix).strip()

        if franchise_key and franchise_key in seen_franchises:
            deferred.append(seed)
            continue
        selected.append(seed)
        if franchise_key:
            seen_franchises.add(franchise_key)
        if len(selected) >= limit:
            return selected

    for seed in deferred:
        selected.append(seed)
        if len(selected) >= limit:
            break
    return selected


def select_negative_signals(
    ratings: list[MediaRating],
    library_entries: list[MediaLibraryEntry],
    *,
    media_type: RecommendationMediaFilter = "all",
    limit: int = 12,
) -> list[NegativeSignal]:
    library_by_key = {
        (entry.media_type, entry.tmdb_id): entry for entry in library_entries
    }
    signals: list[NegativeSignal] = []
    for rating in ratings:
        if media_type != "all" and rating.media_type != media_type:
            continue
        entry = library_by_key.get((rating.media_type, rating.tmdb_id))
        if entry is None:
            continue
        enjoyment = _enjoyment(rating)
        if rating.total >= 67.5 and enjoyment >= 6.5:
            continue

        score_dislike = max(0.0, min(1.0, (67.5 - rating.total) / 40.0))
        enjoyment_dislike = max(0.0, min(1.0, (6.5 - enjoyment) / 5.5))
        weight = max(0.15, 0.62 * score_dislike + 0.38 * enjoyment_dislike)
        signals.append(
            NegativeSignal(
                media_type=rating.media_type,
                tmdb_id=rating.tmdb_id,
                title=entry.title,
                total=rating.total,
                enjoyment=enjoyment,
                weight=weight,
            )
        )

    return sorted(
        signals,
        key=lambda signal: (-signal.weight, signal.total, signal.title.casefold()),
    )[: max(1, limit)]


def build_feature_taste_model(
    weighted_features: list[tuple[float, MediaFeatureProfile]],
) -> FeatureTasteModel:
    genre_sum: defaultdict[int, float] = defaultdict(float)
    genre_norm: defaultdict[int, float] = defaultdict(float)
    genre_occurrences: defaultdict[int, int] = defaultdict(int)
    genre_names: dict[int, str] = {}
    keyword_sum: defaultdict[int, float] = defaultdict(float)
    keyword_norm: defaultdict[int, float] = defaultdict(float)
    keyword_occurrences: defaultdict[int, int] = defaultdict(int)
    keyword_names: dict[int, str] = {}
    creator_sum: defaultdict[str, float] = defaultdict(float)
    creator_norm: defaultdict[str, float] = defaultdict(float)

    sample_count = max(1, len(weighted_features))
    for weight, feature in weighted_features:
        magnitude = abs(weight)
        for genre_id, genre_name in zip(feature.genre_ids, feature.genre_names):
            genre_sum[genre_id] += weight
            genre_norm[genre_id] += magnitude
            genre_occurrences[genre_id] += 1
            genre_names[genre_id] = genre_name
        for keyword_id, keyword_name in zip(feature.keyword_ids, feature.keyword_names):
            keyword_sum[keyword_id] += weight
            keyword_norm[keyword_id] += magnitude
            keyword_occurrences[keyword_id] += 1
            keyword_names[keyword_id] = keyword_name
        for creator in feature.creators:
            key = creator.casefold()
            creator_sum[key] += weight
            creator_norm[key] += magnitude

    return FeatureTasteModel(
        genre_weights={
            key: value / genre_norm[key]
            for key, value in genre_sum.items()
            if genre_norm[key] > 0
        },
        genre_names=genre_names,
        genre_prevalence={
            key: count / sample_count for key, count in genre_occurrences.items()
        },
        keyword_weights={
            key: value / keyword_norm[key]
            for key, value in keyword_sum.items()
            if keyword_norm[key] > 0
        },
        keyword_names=keyword_names,
        keyword_prevalence={
            key: count / sample_count for key, count in keyword_occurrences.items()
        },
        creator_weights={
            key: value / creator_norm[key]
            for key, value in creator_sum.items()
            if creator_norm[key] > 0
        },
    )


def top_positive_genres_for_media(
    weighted_features: list[tuple[float, MediaFeatureProfile]],
    media_type: Literal["movie", "tv"],
    *,
    limit: int = 4,
) -> list[int]:
    totals: defaultdict[int, float] = defaultdict(float)
    norms: defaultdict[int, float] = defaultdict(float)
    occurrences: defaultdict[int, int] = defaultdict(int)
    media_features = [
        (weight, feature)
        for weight, feature in weighted_features
        if feature.media_type == media_type
    ]
    sample_count = max(1, len(media_features))
    for weight, feature in media_features:
        for genre_id in feature.genre_ids:
            totals[genre_id] += weight
            norms[genre_id] += abs(weight)
            occurrences[genre_id] += 1

    scored = [
        (
            (totals[genre_id] / norms[genre_id])
            * max(0.3, 1.0 - 0.7 * (occurrences[genre_id] / sample_count)),
            genre_id,
        )
        for genre_id in totals
        if norms[genre_id] > 0
    ]
    return [
        genre_id
        for score, genre_id in sorted(scored, key=lambda item: (-item[0], item[1]))
        if score > 0.08
    ][:limit]


def rank_candidates(
    candidates: dict[tuple[str, int], CandidateAccumulator],
    library_by_key: dict[tuple[str, int], MediaLibraryEntry],
    *,
    taste_model: FeatureTasteModel | None = None,
    features_by_key: dict[tuple[str, int], MediaFeatureProfile] | None = None,
    dismissed_keys: set[tuple[str, int]] | None = None,
    media_filter: RecommendationMediaFilter = "all",
    discovery_mode: RecommendationDiscoveryMode = "balanced",
) -> list[RecommendationItem]:
    ranked: list[RecommendationItem] = []
    features_by_key = features_by_key or {}
    dismissed_keys = dismissed_keys or set()

    for key, candidate in candidates.items():
        if key in dismissed_keys:
            continue
        library_entry = library_by_key.get(key)
        if library_entry is not None and library_entry.status in {
            "watched",
            "watching",
            "dropped",
        }:
            continue

        support = sorted(
            candidate.seeds.values(),
            key=lambda seed: (-seed.weight, seed.title.casefold()),
        )
        if not _passes_candidate_quality_gate(
            candidate.media,
            len(support),
            media_filter,
            discovery_mode,
        ):
            continue
        feature = features_by_key.get(key)
        if feature is None:
            feature = MediaFeatureProfile(
                media_type=candidate.media.media_type,
                tmdb_id=candidate.media.tmdb_id,
                genre_ids=list(candidate.media.genre_ids),
                original_language=candidate.media.original_language,
                is_anime=_candidate_is_anime(candidate.media),
            )

        feature_score, positive_genres = _feature_match_score(taste_model, feature)
        alignment = max(0.25, min(1.0, (feature_score + 12.0) / 34.0))
        support_score = min(18.0, sum(seed.weight for seed in support) * 6.0) * alignment
        consensus = min(6.0, max(0, len(support) - 1) * 1.9) * alignment
        reliability = min(1.0, log10(max(candidate.vote_count, 0) + 1) / 4.0)
        audience_center = (max(0.0, min(10.0, candidate.vote_average)) - 5.8) / 4.2
        audience_score = max(-5.0, min(8.0, audience_center * 8.0 * reliability))
        familiarity_score = _familiarity_score(
            candidate.vote_count,
            candidate.popularity,
            discovery_mode,
        )

        favourite_bonus = 2.0 if any(seed.favourite for seed in support) else 0.0
        watchlist_bonus = 2.0 if library_entry and library_entry.status == "watchlist" else 0.0
        discovery_bonus = 1.5 if candidate.discovered and not support else 0.0
        score = round(
            max(
                0.0,
                min(
                    99.0,
                    42.0
                    + support_score
                    + consensus
                    + feature_score
                    + audience_score
                    + familiarity_score
                    + favourite_bonus
                    + watchlist_bonus
                    + discovery_bonus,
                ),
            ),
            1,
        )

        reasons = _candidate_reasons(
            support=support,
            positive_genres=positive_genres,
            vote_average=candidate.vote_average,
            vote_count=candidate.vote_count,
            discovered=candidate.discovered,
            on_watchlist=bool(library_entry and library_entry.status == "watchlist"),
        )
        ranked.append(
            RecommendationItem(
                media_type=candidate.media.media_type,
                tmdb_id=candidate.media.tmdb_id,
                title=candidate.media.title,
                year=candidate.media.year,
                overview=candidate.media.overview,
                poster_path=candidate.media.poster_path,
                is_anime=feature.is_anime,
                match_score=score,
                tmdb_vote_average=round(candidate.vote_average, 1),
                tmdb_vote_count=candidate.vote_count,
                seed_titles=[seed.title for seed in support[:3]],
                reasons=reasons,
                on_watchlist=bool(library_entry and library_entry.status == "watchlist"),
                genre_names=list(feature.genre_names),
                collection_id=feature.collection_id,
                collection_name=feature.collection_name,
                providers=[],
            )
        )

    return sorted(
        ranked,
        key=lambda item: (
            -item.match_score,
            -item.tmdb_vote_count,
            item.title.casefold(),
        ),
    )


def diversify_recommendations(
    items: list[RecommendationItem],
    *,
    limit: int,
) -> list[RecommendationItem]:
    """Greedily select a varied list without lying about the displayed match score."""
    remaining = list(items)
    selected: list[RecommendationItem] = []
    franchise_counts: defaultdict[str, int] = defaultdict(int)

    while remaining and len(selected) < max(0, limit):
        best_index = 0
        best_adjusted = float("-inf")
        for index, item in enumerate(remaining):
            adjusted = item.match_score
            franchise_key = _franchise_key(item)
            if franchise_key:
                adjusted -= 30.0 * franchise_counts[franchise_key]

            item_genres = {name.casefold() for name in item.genre_names}
            if item_genres and selected:
                max_overlap = 0.0
                for previous in selected:
                    previous_genres = {name.casefold() for name in previous.genre_names}
                    union = item_genres | previous_genres
                    if not union:
                        continue
                    max_overlap = max(max_overlap, len(item_genres & previous_genres) / len(union))
                if max_overlap >= 0.75:
                    adjusted -= 6.0
                elif max_overlap >= 0.5:
                    adjusted -= 3.0

            if adjusted > best_adjusted:
                best_adjusted = adjusted
                best_index = index

        chosen = remaining.pop(best_index)
        selected.append(chosen)
        franchise_key = _franchise_key(chosen)
        if franchise_key:
            franchise_counts[franchise_key] += 1

    return selected


def _candidate_is_anime(candidate: RecommendationCandidate) -> bool:
    return (
        candidate.original_language == "ja"
        and ANIMATION_GENRE_ID in candidate.genre_ids
    )


def _feature_matches_filter(
    feature: MediaFeatureProfile,
    media_filter: RecommendationMediaFilter,
) -> bool:
    if media_filter == "all":
        return True
    if media_filter == "movie":
        return feature.media_type == "movie"
    if media_filter == "tv":
        return feature.media_type == "tv" and ANIMATION_GENRE_ID not in feature.genre_ids
    if media_filter == "anime":
        return feature.is_anime
    return False


def _candidate_matches_filter(
    candidate: RecommendationCandidate,
    media_filter: RecommendationMediaFilter,
) -> bool:
    if media_filter == "all":
        return True
    if media_filter == "movie":
        return candidate.media_type == "movie"
    if media_filter == "tv":
        return candidate.media_type == "tv" and ANIMATION_GENRE_ID not in candidate.genre_ids
    if media_filter == "anime":
        return _candidate_is_anime(candidate)
    return False


def _passes_candidate_quality_gate(
    candidate: RecommendationCandidate,
    support_count: int,
    media_filter: RecommendationMediaFilter,
    discovery_mode: RecommendationDiscoveryMode = "balanced",
) -> bool:
    """Reject thin TMDB entries according to the requested discovery style."""
    base_thresholds = {
        "familiar": {"tv": 800, "anime": 200, "movie": 800, "all": 500},
        "balanced": {"tv": 250, "anime": 50, "movie": 75, "all": 50},
        "hidden": {"tv": 40, "anime": 15, "movie": 25, "all": 20},
    }
    minimum_votes = base_thresholds[discovery_mode][media_filter]
    if support_count >= 3:
        minimum_votes = max(20, int(minimum_votes * 0.45))
    elif support_count >= 2:
        minimum_votes = max(20, int(minimum_votes * 0.65))
    return candidate.vote_count >= minimum_votes


def _accumulate_candidate(
    candidates: dict[tuple[str, int], CandidateAccumulator],
    candidate: RecommendationCandidate,
) -> CandidateAccumulator:
    key = (candidate.media_type, candidate.tmdb_id)
    accumulator = candidates.get(key)
    if accumulator is None:
        accumulator = CandidateAccumulator(
            media=candidate,
            vote_average=float(candidate.vote_average or 0.0),
            vote_count=int(candidate.vote_count or 0),
            popularity=float(candidate.popularity or 0.0),
        )
        candidates[key] = accumulator
    return accumulator


def _feature_match_score(
    model: FeatureTasteModel | None,
    feature: MediaFeatureProfile,
) -> tuple[float, list[str]]:
    if model is None:
        return 0.0, []

    genre_values = [
        model.genre_weights[key]
        * max(0.3, 1.0 - 0.7 * model.genre_prevalence.get(key, 0.0))
        for key in feature.genre_ids
        if key in model.genre_weights
    ]
    keyword_values = [
        model.keyword_weights[key]
        * max(0.45, 1.0 - 0.5 * model.keyword_prevalence.get(key, 0.0))
        for key in feature.keyword_ids
        if key in model.keyword_weights
    ]
    creator_values = [
        model.creator_weights[name.casefold()]
        for name in feature.creators
        if name.casefold() in model.creator_weights
    ]

    genre_signal = sum(genre_values) / len(genre_values) if genre_values else 0.0
    keyword_signal = sum(keyword_values) / len(keyword_values) if keyword_values else 0.0
    creator_signal = max(creator_values, default=0.0)
    score = genre_signal * 15.0 + keyword_signal * 9.0 + creator_signal * 7.0

    positive_genres = sorted(
        (
            (
                model.genre_weights.get(genre_id, 0.0)
                * max(0.3, 1.0 - 0.7 * model.genre_prevalence.get(genre_id, 0.0)),
                genre_name,
            )
            for genre_id, genre_name in zip(feature.genre_ids, feature.genre_names)
            if model.genre_weights.get(genre_id, 0.0) > 0.18
        ),
        key=lambda item: (-item[0], item[1].casefold()),
    )
    return max(-24.0, min(30.0, score)), [name for _, name in positive_genres[:3]]


def _familiarity_score(
    vote_count: int,
    popularity: float,
    discovery_mode: RecommendationDiscoveryMode,
) -> float:
    vote_signal = min(1.0, log10(max(vote_count, 0) + 1) / 4.2)
    popularity_signal = min(1.0, max(0.0, popularity) / 120.0)
    combined = 0.8 * vote_signal + 0.2 * popularity_signal
    if discovery_mode == "familiar":
        return combined * 9.0
    if discovery_mode == "balanced":
        return combined * 4.0
    # Hidden-gem mode deliberately removes the popularity advantage rather than
    # punishing well-known titles outright.
    return 0.0


def _candidate_reasons(
    *,
    support: list[RecommendationSeed],
    positive_genres: list[str],
    vote_average: float,
    vote_count: int,
    discovered: bool,
    on_watchlist: bool,
) -> list[str]:
    reasons: list[str] = []
    if positive_genres:
        reasons.append("Taste match: " + ", ".join(positive_genres) + ".")

    titles = [seed.title for seed in support[:2]]
    if len(support) >= 2:
        extra = len(support) - len(titles)
        suffix = f" +{extra} more" if extra > 0 else ""
        reasons.append(
            f"Backed by {len(support)} of your highly rated titles: "
            + " and ".join(titles)
            + suffix
            + "."
        )
    elif titles:
        reasons.append(f"Related to {titles[0]}, which you rated highly.")
    elif discovered:
        reasons.append("Found from genres that score well across your ratings.")

    if vote_count >= 200 and vote_average > 0:
        reasons.append(f"TMDB {vote_average:.1f}/10 from {vote_count:,} votes.")
    if on_watchlist:
        reasons.append("Already on your watchlist.")
    return reasons[:3]


def _availability_reason(providers) -> str:
    provider = providers[0]
    if not provider.countries:
        return f"Available on {provider.service_name}."
    first_country = provider.countries[0].name
    extra = len(provider.countries) - 1
    suffix = f" +{extra} more countries" if extra > 0 else ""
    return f"Available on {provider.service_name} in {first_country}{suffix}."


def _franchise_key(item: RecommendationItem) -> str | None:
    if item.collection_id is not None:
        return f"collection:{item.collection_id}"
    title = item.title.casefold().strip()
    if ":" in title:
        prefix = title.split(":", 1)[0].strip()
        if len(prefix) >= 4:
            return "title:" + re.sub(r"[^a-z0-9]+", " ", prefix).strip()
    return None


def _enjoyment(rating: MediaRating) -> float:
    return next(
        (score.score for score in rating.categories if score.key == "enjoyment"),
        rating.total / 10.0,
    )


def _response_message(*, count: int, only_my_services: bool, generated_from: int) -> str:
    if count == 0:
        if only_my_services:
            return (
                "No strong candidates from the current taste profile were found on your "
                "selected services. Try another recommendation mode or turn off the availability filter."
            )
        return "No recommendation candidates were returned from the current taste profile."
    availability = " available on your selected services" if only_my_services else ""
    return (
        f"Found {count} diversified personalised recommendation(s){availability} "
        f"from {generated_from} positive seed title(s)."
    )
