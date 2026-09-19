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
from app.services.media_metadata import MediaMetadataService
from app.services.metadata_taste import build_weighted_feature_inputs

RecommendationMediaFilter = Literal["all", "movie", "tv", "anime", "anime_movie", "anime_tv"]
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
        *,
        metadata: MediaMetadataService | None = None,
    ) -> None:
        self.tmdb = tmdb
        self.library = library
        self.ratings = ratings
        self.preferences = preferences
        self.dismissals = dismissals
        self.metadata = metadata
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
        if media_type == "anime":
            return await self._recommend_mixed_anime(
                limit=limit,
                only_my_services=only_my_services,
                discovery_mode=discovery_mode,
            )

        ratings = self.ratings.list()
        library_entries = self.library.list()

        # TV and anime share TMDB's "tv" media type, so pull a broader signal
        # pool first, classify it using TMDB metadata, then build a subtype-specific
        # taste model. This stops a large anime library from hijacking live-action TV.
        if media_type == "anime_movie":
            signal_media_type: RecommendationMediaFilter = "movie"
        elif media_type == "anime_tv":
            signal_media_type = "tv"
        else:
            signal_media_type = media_type
        signal_pool = 24 if media_type in {"tv", "anime_movie", "anime_tv"} else 12
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
            limit=16 if media_type in {"tv", "anime_movie", "anime_tv"} else 8,
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
            subtype = {
                "tv": "live-action TV",
                "anime_movie": "anime movie",
                "anime_tv": "anime series",
            }.get(media_type, "matching")
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
        # V0.13 then broadens this with continuous signals from the full rated history,
        # so one favourite franchise cannot define the user's entire metadata profile.
        allowed_keys = {
            (item.media_type, item.tmdb_id) for item in [*seeds, *negatives]
        }
        weighted_features = [
            (weight, feature)
            for weight, feature in weighted_features
            if (feature.media_type, feature.tmdb_id) in allowed_keys
        ]

        history_ratings = [
            rating
            for rating in ratings
            if media_type == "all"
            or (media_type == "anime_movie" and rating.media_type == "movie")
            or (media_type == "anime_tv" and rating.media_type == "tv")
            or rating.media_type == media_type
        ]
        history_results = await asyncio.gather(
            *(self._get_features(rating.media_type, rating.tmdb_id) for rating in history_ratings),
            return_exceptions=True,
        )
        history_features: dict[tuple[str, int], MediaFeatureProfile] = {}
        for rating, result in zip(history_ratings, history_results, strict=True):
            if isinstance(result, Exception):
                continue
            if not _feature_matches_filter(result, media_type):
                continue
            history_features[(rating.media_type, rating.tmdb_id)] = result

        full_history_weights = build_weighted_feature_inputs(
            ratings,
            library_entries,
            history_features,
        )
        if len(full_history_weights) >= 4:
            weighted_features = full_history_weights

        taste_model = build_feature_taste_model(weighted_features)
        seed_source = seeds
        active_seeds = diversify_recommendation_seeds(
            seed_source,
            features_for_signals,
            limit=min(8, len(seed_source)),
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
        if media_type == "all":
            discover_types = ["movie", "tv"]
        elif media_type == "anime_movie":
            discover_types = ["movie"]
        elif media_type == "anime_tv":
            discover_types = ["tv"]
        else:
            discover_types = [media_type]
        if hasattr(self.tmdb, "discover_media"):
            discovery_jobs = []
            subtype_history_size = len(history_features)
            discovery_pages = _discovery_pages(
                media_type,
                discovery_mode,
                subtype_history_size=subtype_history_size,
            )

            # Anime needs a broader discovery pool than ordinary movie/TV modes.
            # TMDB stores anime series as generic TV and anime films as generic
            # movies, so relying only on the user's strongest genre combination can
            # become far too restrictive once a mature library has already consumed
            # the obvious titles. For anime subtypes we therefore run:
            #   1. a broad Japanese Animation query across all discovery pages; and
            #   2. several single-genre taste queries on page 1.
            # The local taste model still decides the final ranking.
            discovery_requests: list[tuple[Literal["movie", "tv"], list[int], list[int]]] = []
            for kind in discover_types:
                genres = top_positive_genres_for_media(
                    weighted_features,
                    kind,
                    limit=4,
                )
                if media_type in {"anime_movie", "anime_tv"}:
                    discovery_requests.append((kind, [], discovery_pages))
                    taste_genres = [
                        genre_id
                        for genre_id in genres
                        if genre_id != ANIMATION_GENRE_ID
                    ][:3]
                    discovery_requests.extend(
                        (kind, [genre_id], [1]) for genre_id in taste_genres
                    )
                elif genres:
                    discovery_requests.append((kind, genres, discovery_pages))

            for kind, genres, pages in discovery_requests:
                kwargs: dict[str, object] = {
                    "sort_by": (
                        "popularity.desc"
                        if discovery_mode == "familiar"
                        else "vote_average.desc"
                    )
                }
                if media_type in {"anime_movie", "anime_tv"}:
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
                for page in pages:
                    discovery_jobs.append(
                        self.tmdb.discover_media(kind, genres, page=page, **kwargs)
                    )

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
        enrichment_limit = min(max(limit * 2, 18), 24)
        enrichment_pool = preliminary[:enrichment_limit]
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
        pool = diversify_recommendations(
            ranked,
            limit=pool_limit,
            media_filter=media_type,
        )

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
            items = diversify_recommendations(
                available,
                limit=limit,
                media_filter=media_type,
            )
        else:
            items = diversify_recommendations(
                pool,
                limit=limit,
                media_filter=media_type,
            )

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

    async def _recommend_mixed_anime(
        self,
        *,
        limit: int,
        only_my_services: bool,
        discovery_mode: RecommendationDiscoveryMode,
    ) -> RecommendationResponse:
        """Build mixed anime from two independent subtype pipelines.

        TMDB stores anime films as ``movie`` and anime series as ``tv``. Keeping
        those pipelines separate until the final merge prevents one subtype from
        erasing the other during candidate generation, metadata enrichment, or
        availability filtering.
        """
        movie_response, tv_response = await asyncio.gather(
            self.recommend(
                media_type="anime_movie",
                limit=limit,
                only_my_services=only_my_services,
                discovery_mode=discovery_mode,
            ),
            self.recommend(
                media_type="anime_tv",
                limit=limit,
                only_my_services=only_my_services,
                discovery_mode=discovery_mode,
            ),
        )

        merged = sorted(
            [*movie_response.items, *tv_response.items],
            key=lambda item: (-item.match_score, -item.tmdb_vote_count, item.title.casefold()),
        )
        items = balance_media_type_mix(merged, limit=limit)
        movie_count = sum(item.media_type == "movie" for item in items)
        tv_count = sum(item.media_type == "tv" for item in items)

        if items:
            message = (
                f"Found {len(items)} mixed anime recommendation(s): "
                f"{tv_count} series and {movie_count} movie(s)."
            )
            if only_my_services:
                message += " All are available on your selected services."
        else:
            message = (
                "No mixed anime recommendations matched the current filters. "
                "Try turning off Only my services or using Balanced discovery."
            )

        return RecommendationResponse(
            media_filter="anime",
            discovery_mode=discovery_mode,
            only_my_services=only_my_services,
            generated_from=movie_response.generated_from + tv_response.generated_from,
            total_considered=movie_response.total_considered + tv_response.total_considered,
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
        if self.metadata is not None:
            result = await self.metadata.get(media_type, tmdb_id)
        else:
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

        feature_score, positive_matches = _feature_match_score(taste_model, feature)
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
            positive_matches=positive_matches,
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


def balance_media_type_mix(items: list, *, limit: int) -> list:
    """Preserve both movie and TV items when a mixed result set contains both.

    The input is assumed to already be ranked best-to-worst. The helper keeps
    roughly half the requested slots for each TMDB media type, then fills any
    unused capacity from the strongest remaining entries. It is intentionally
    generic so the same rule can be applied to seeds and recommendation items.
    """
    if limit <= 0:
        return []
    ranked = list(items)
    if len(ranked) <= 1:
        return ranked[:limit]

    movies = [item for item in ranked if getattr(item, "media_type", None) == "movie"]
    tv = [item for item in ranked if getattr(item, "media_type", None) == "tv"]
    if not movies or not tv:
        return ranked[:limit]

    half = limit // 2
    movie_target = min(len(movies), half)
    tv_target = min(len(tv), half)
    chosen_ids = {id(item) for item in movies[:movie_target]} | {
        id(item) for item in tv[:tv_target]
    }

    remaining_slots = limit - len(chosen_ids)
    if remaining_slots > 0:
        for item in ranked:
            if id(item) in chosen_ids:
                continue
            chosen_ids.add(id(item))
            remaining_slots -= 1
            if remaining_slots <= 0:
                break

    return [item for item in ranked if id(item) in chosen_ids][:limit]


def diversify_recommendations(
    items: list[RecommendationItem],
    *,
    limit: int,
    media_filter: RecommendationMediaFilter = "all",
) -> list[RecommendationItem]:
    """Greedily select a varied list without lying about the displayed match score.

    Mixed anime is special because TMDB stores anime films as ``movie`` and
    anime series as ``tv``. Without an explicit subtype balance, one side can
    consume the whole page even when good candidates exist for both.
    """
    if media_filter != "anime":
        return _diversify_recommendations_core(items, limit=limit)

    balanced_source = balance_media_type_mix(items, limit=min(len(items), max(limit * 2, limit)))
    movies = [item for item in balanced_source if item.media_type == "movie"]
    tv = [item for item in balanced_source if item.media_type == "tv"]
    if not movies or not tv:
        return _diversify_recommendations_core(items, limit=limit)

    half = limit // 2
    movie_target = min(len(movies), half)
    tv_target = min(len(tv), half)
    selected = [
        *_diversify_recommendations_core(movies, limit=movie_target),
        *_diversify_recommendations_core(tv, limit=tv_target),
    ]

    selected_keys = {(item.media_type, item.tmdb_id) for item in selected}
    remaining_slots = limit - len(selected)
    if remaining_slots > 0:
        leftovers = [
            item
            for item in items
            if (item.media_type, item.tmdb_id) not in selected_keys
        ]
        selected.extend(
            _diversify_recommendations_core(leftovers, limit=remaining_slots)
        )

    original_rank = {
        (item.media_type, item.tmdb_id): index for index, item in enumerate(items)
    }
    selected.sort(key=lambda item: original_rank.get((item.media_type, item.tmdb_id), 10**9))
    return selected[:limit]


def _diversify_recommendations_core(
    items: list[RecommendationItem],
    *,
    limit: int,
) -> list[RecommendationItem]:
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
                    max_overlap = max(
                        max_overlap,
                        len(item_genres & previous_genres) / len(union),
                    )
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



def _discovery_pages(
    media_filter: RecommendationMediaFilter,
    discovery_mode: RecommendationDiscoveryMode,
    *,
    subtype_history_size: int,
) -> list[int]:
    """Choose how deeply to search TMDB discovery results.

    Mature libraries quickly exhaust page 1 because popular titles have already
    been watched. Anime series are especially affected, so deeper pagination is
    intentional there rather than lowering quality thresholds.
    """
    if media_filter == "anime_tv":
        base = {"familiar": 3, "balanced": 3, "hidden": 2}[discovery_mode]
        if subtype_history_size >= 40:
            base += 2
        elif subtype_history_size >= 20:
            base += 1
        return list(range(1, min(base, 6) + 1))

    if media_filter == "anime_movie":
        base = {"familiar": 2, "balanced": 2, "hidden": 2}[discovery_mode]
        if subtype_history_size >= 20:
            base += 1
        return list(range(1, min(base, 4) + 1))

    # A second page helps mature live-action libraries without multiplying
    # network traffic for small collections.
    if subtype_history_size >= 40 and media_filter in {"movie", "tv"}:
        return [1, 2]
    return [1]

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
    if media_filter == "anime_movie":
        return feature.media_type == "movie" and feature.is_anime
    if media_filter == "anime_tv":
        return feature.media_type == "tv" and feature.is_anime
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
    if media_filter == "anime_movie":
        return candidate.media_type == "movie" and _candidate_is_anime(candidate)
    if media_filter == "anime_tv":
        return candidate.media_type == "tv" and _candidate_is_anime(candidate)
    return False


def _passes_candidate_quality_gate(
    candidate: RecommendationCandidate,
    support_count: int,
    media_filter: RecommendationMediaFilter,
    discovery_mode: RecommendationDiscoveryMode = "balanced",
) -> bool:
    """Reject thin TMDB entries according to the requested discovery style."""
    base_thresholds = {
        "familiar": {"tv": 800, "anime": 200, "anime_movie": 200, "anime_tv": 200, "movie": 800, "all": 500},
        "balanced": {"tv": 250, "anime": 50, "anime_movie": 50, "anime_tv": 50, "movie": 75, "all": 50},
        "hidden": {"tv": 40, "anime": 15, "anime_movie": 15, "anime_tv": 15, "movie": 25, "all": 20},
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
    positive_keywords = sorted(
        (
            (
                model.keyword_weights.get(keyword_id, 0.0)
                * max(0.45, 1.0 - 0.5 * model.keyword_prevalence.get(keyword_id, 0.0)),
                keyword_name,
            )
            for keyword_id, keyword_name in zip(feature.keyword_ids, feature.keyword_names)
            if model.keyword_weights.get(keyword_id, 0.0) > 0.24
        ),
        key=lambda item: (-item[0], item[1].casefold()),
    )
    positive_creators = sorted(
        (
            (model.creator_weights.get(name.casefold(), 0.0), name)
            for name in feature.creators
            if model.creator_weights.get(name.casefold(), 0.0) > 0.22
        ),
        key=lambda item: (-item[0], item[1].casefold()),
    )
    matches: list[str] = []
    for _score, name in [*positive_genres[:2], *positive_keywords[:1], *positive_creators[:1]]:
        if name not in matches:
            matches.append(name)
    return max(-24.0, min(30.0, score)), matches[:3]


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
    positive_matches: list[str],
    vote_average: float,
    vote_count: int,
    discovered: bool,
    on_watchlist: bool,
) -> list[str]:
    reasons: list[str] = []
    if positive_matches:
        reasons.append("Taste match: " + ", ".join(positive_matches) + ".")

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
