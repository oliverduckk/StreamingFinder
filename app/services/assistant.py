from __future__ import annotations

from collections import Counter

from app.clients.tmdb import TMDBClient
from app.models.assistant import (
    AssistantLibrarySummary,
    AssistantProfileResponse,
    AssistantTitleContextResponse,
    AssistantTitleResolution,
    AssistantWhereToWatchResponse,
)
from app.models.media import MediaSearchResult, MediaType, RecommendationResponse
from app.repositories.features import MediaFeatureRepository
from app.repositories.library import MediaLibraryRepository
from app.repositories.preferences import StreamingPreferencesRepository
from app.repositories.ratings import MediaRatingRepository
from app.repositories.recommendation_feedback import RecommendationFeedbackRepository
from app.services.metadata_taste import build_metadata_taste_profile
from app.services.ratings_dashboard import build_ratings_dashboard
from app.services.recommendations import (
    RecommendationDiscoveryMode,
    RecommendationMediaFilter,
    RecommendationService,
)
from app.services.taste_profile import build_taste_profile


class AssistantService:
    """Small tool-oriented facade over StreamingFinder's lower-level services.

    This deliberately returns structured data rather than conversational prose so
    Mairon (or any future assistant/client) can decide how to phrase the answer.
    """

    def __init__(
        self,
        tmdb: TMDBClient,
        library: MediaLibraryRepository,
        ratings: MediaRatingRepository,
        preferences: StreamingPreferencesRepository,
        recommendations: RecommendationService,
        feedback: RecommendationFeedbackRepository,
        features: MediaFeatureRepository,
    ) -> None:
        self.tmdb = tmdb
        self.library = library
        self.ratings = ratings
        self.preferences = preferences
        self.recommendations = recommendations
        self.feedback = feedback
        self.features = features

    async def resolve_title(
        self,
        query: str,
        *,
        media_type: MediaType | None = None,
        year: int | None = None,
    ) -> AssistantTitleResolution:
        clean_query = query.strip()
        if not clean_query:
            raise LookupError("A title is required.")

        results = await self.tmdb.search_media(clean_query)
        if media_type is not None:
            results = [item for item in results if item.media_type == media_type]
        if not results:
            raise LookupError(f"No matching movie or TV title was found for {clean_query!r}.")

        selected = _select_best_match(results, clean_query, year=year)
        alternatives = [item for item in results if item != selected][:4]
        exact_title_match = _normalise_title(selected.title) == _normalise_title(clean_query)
        year_match = None if year is None else selected.year == year
        return AssistantTitleResolution(
            query=clean_query,
            selected=selected,
            alternatives=alternatives,
            exact_title_match=exact_title_match,
            year_match=year_match,
        )

    async def where_to_watch(
        self,
        query: str,
        *,
        media_type: MediaType | None = None,
        year: int | None = None,
        only_my_services: bool = True,
    ) -> AssistantWhereToWatchResponse:
        resolution = await self.resolve_title(query, media_type=media_type, year=year)
        service_keys = self.preferences.get_enabled_services() if only_my_services else []
        availability = await self.tmdb.get_subscription_availability(
            resolution.selected.media_type,
            resolution.selected.tmdb_id,
            service_keys=set(service_keys) if only_my_services else None,
        )
        return AssistantWhereToWatchResponse(
            resolution=resolution,
            only_my_services=only_my_services,
            services_considered=service_keys,
            availability=availability,
        )

    async def title_context(
        self,
        query: str,
        *,
        media_type: MediaType | None = None,
        year: int | None = None,
        include_availability: bool = False,
        only_my_services: bool = True,
    ) -> AssistantTitleContextResponse:
        resolution = await self.resolve_title(query, media_type=media_type, year=year)
        selected = resolution.selected
        library_entry = self.library.get(selected.media_type, selected.tmdb_id)
        rating = self.ratings.get(selected.media_type, selected.tmdb_id)
        availability = None
        if include_availability:
            service_keys = self.preferences.get_enabled_services() if only_my_services else []
            availability = await self.tmdb.get_subscription_availability(
                selected.media_type,
                selected.tmdb_id,
                service_keys=set(service_keys) if only_my_services else None,
            )

        return AssistantTitleContextResponse(
            resolution=resolution,
            library_entry=library_entry,
            rating=rating,
            watched=bool(library_entry and library_entry.status == "watched"),
            on_watchlist=bool(library_entry and library_entry.status == "watchlist"),
            availability=availability,
        )

    async def recommend(
        self,
        *,
        media_type: RecommendationMediaFilter = "all",
        limit: int = 5,
        only_my_services: bool = True,
        discovery_mode: RecommendationDiscoveryMode = "familiar",
    ) -> RecommendationResponse:
        return await self.recommendations.recommend(
            media_type=media_type,
            limit=limit,
            only_my_services=only_my_services,
            discovery_mode=discovery_mode,
        )

    def profile(self) -> AssistantProfileResponse:
        library_entries = self.library.list()
        ratings = self.ratings.list()
        status_counts = Counter(entry.status for entry in library_entries)
        features_by_key = {}
        for rating in ratings:
            profile = self.features.get(rating.media_type, rating.tmdb_id)
            if profile is not None:
                features_by_key[(rating.media_type, rating.tmdb_id)] = profile

        return AssistantProfileResponse(
            library=AssistantLibrarySummary(
                total=len(library_entries),
                watchlist=status_counts.get("watchlist", 0),
                watching=status_counts.get("watching", 0),
                watched=status_counts.get("watched", 0),
                dropped=status_counts.get("dropped", 0),
                favourites=sum(1 for entry in library_entries if entry.favourite),
            ),
            ratings=build_ratings_dashboard(ratings, library_entries),
            taste=build_taste_profile(ratings, library_entries),
            metadata=build_metadata_taste_profile(ratings, library_entries, features_by_key),
            recommendation_feedback=self.feedback.summary(),
        )


def _select_best_match(
    results: list[MediaSearchResult],
    query: str,
    *,
    year: int | None,
) -> MediaSearchResult:
    normalised_query = _normalise_title(query)

    def score(item_with_index: tuple[int, MediaSearchResult]) -> tuple[int, int]:
        index, item = item_with_index
        value = 0
        normalised_title = _normalise_title(item.title)
        if normalised_title == normalised_query:
            value += 100
        elif normalised_title.startswith(normalised_query):
            value += 30
        elif normalised_query in normalised_title:
            value += 15
        if year is not None and item.year == year:
            value += 60
        return value, -index

    return max(enumerate(results), key=score)[1]


def _normalise_title(value: str) -> str:
    return " ".join(value.casefold().strip().split())
