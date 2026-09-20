from pathlib import Path

import pytest

from app.db.database import SQLiteDatabase
from app.models.media import (
    CountryAvailability,
    MediaAvailability,
    MediaSearchResult,
    RecommendationResponse,
    StreamingServiceAvailability,
)
from app.repositories.features import MediaFeatureRepository
from app.repositories.library import MediaLibraryRepository
from app.repositories.preferences import StreamingPreferencesRepository
from app.repositories.ratings import MediaRatingRepository
from app.repositories.recommendation_feedback import RecommendationFeedbackRepository
from app.services.assistant import AssistantService
from app.services.rating_system import RATING_CATEGORY_KEYS


class FakeTMDB:
    def __init__(self) -> None:
        self.received_service_keys: set[str] | None = None

    async def search_media(self, query: str):
        return [
            MediaSearchResult(
                tmdb_id=157336,
                media_type="movie",
                title="Interstellar",
                year=2014,
                overview="Space.",
            ),
            MediaSearchResult(
                tmdb_id=212171,
                media_type="tv",
                title="Interstellar Ella",
                year=2022,
            ),
        ]

    async def get_subscription_availability(
        self,
        media_type,
        tmdb_id,
        service_keys=None,
    ):
        self.received_service_keys = service_keys
        return MediaAvailability(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title="Interstellar",
            year=2014,
            providers=[
                StreamingServiceAvailability(
                    service_key="netflix",
                    service_name="Netflix",
                    provider_ids=[8],
                    countries=[CountryAvailability(code="JP", name="Japan")],
                )
            ],
        )


class FakeRecommendations:
    async def recommend(
        self,
        *,
        media_type="all",
        limit=5,
        only_my_services=True,
        discovery_mode="familiar",
    ):
        return RecommendationResponse(
            media_filter=media_type,
            discovery_mode=discovery_mode,
            only_my_services=only_my_services,
            generated_from=3,
            total_considered=10,
            message="Three good options.",
            items=[],
        )


def make_service(tmp_path: Path):
    database = SQLiteDatabase(tmp_path / "assistant.db")
    library = MediaLibraryRepository(database)
    ratings = MediaRatingRepository(database)
    preferences = StreamingPreferencesRepository(database)
    feedback = RecommendationFeedbackRepository(database)
    features = MediaFeatureRepository(database)
    tmdb = FakeTMDB()
    service = AssistantService(
        tmdb,
        library,
        ratings,
        preferences,
        FakeRecommendations(),  # type: ignore[arg-type]
        feedback,
        features,
    )
    return service, tmdb, library, ratings, preferences, feedback


@pytest.mark.anyio
async def test_where_to_watch_prefers_exact_title_and_saved_services(tmp_path: Path) -> None:
    service, tmdb, _library, _ratings, preferences, _feedback = make_service(tmp_path)
    preferences.set_enabled_services({"netflix", "prime_video"})

    result = await service.where_to_watch("Interstellar")

    assert result.resolution.selected.tmdb_id == 157336
    assert result.resolution.exact_title_match is True
    assert result.services_considered == ["netflix", "prime_video"]
    assert tmdb.received_service_keys == {"netflix", "prime_video"}
    assert result.availability.providers[0].countries[0].name == "Japan"


@pytest.mark.anyio
async def test_title_context_returns_library_and_structured_rating(tmp_path: Path) -> None:
    service, _tmdb, library, ratings, _preferences, _feedback = make_service(tmp_path)
    media = MediaSearchResult(
        tmdb_id=157336,
        media_type="movie",
        title="Interstellar",
        year=2014,
    )
    library.upsert(media, "watched", favourite=True)
    ratings.upsert(
        "movie",
        157336,
        {key: 9.0 for key in RATING_CATEGORY_KEYS},
        notes="Great film.",
    )

    result = await service.title_context("Interstellar")

    assert result.watched is True
    assert result.on_watchlist is False
    assert result.library_entry is not None
    assert result.library_entry.favourite is True
    assert result.rating is not None
    assert result.rating.total == 90.0
    assert result.rating.notes == "Great film."


def test_profile_summarises_local_library_and_feedback(tmp_path: Path) -> None:
    service, _tmdb, library, ratings, _preferences, feedback = make_service(tmp_path)
    watched = MediaSearchResult(
        tmdb_id=157336,
        media_type="movie",
        title="Interstellar",
        year=2014,
    )
    watchlist = MediaSearchResult(
        tmdb_id=550,
        media_type="movie",
        title="Fight Club",
        year=1999,
    )
    library.upsert(watched, "watched", favourite=True)
    library.upsert(watchlist, "watchlist")
    ratings.upsert(
        "movie",
        157336,
        {key: 8.0 for key in RATING_CATEGORY_KEYS},
    )
    feedback.record("movie", 550, "Fight Club", "watchlist")

    profile = service.profile()

    assert profile.library.total == 2
    assert profile.library.watched == 1
    assert profile.library.watchlist == 1
    assert profile.library.favourites == 1
    assert profile.ratings.total_rated == 1
    assert profile.recommendation_feedback.watchlisted == 1


@pytest.mark.anyio
async def test_assistant_recommendations_use_tool_friendly_defaults(tmp_path: Path) -> None:
    service, *_ = make_service(tmp_path)

    result = await service.recommend()

    assert result.discovery_mode == "familiar"
    assert result.only_my_services is True
    assert result.generated_from == 3


@pytest.mark.anyio
async def test_missing_title_raises_lookup_error(tmp_path: Path) -> None:
    service, tmdb, *_ = make_service(tmp_path)

    async def no_results(_query: str):
        return []

    tmdb.search_media = no_results  # type: ignore[method-assign]

    with pytest.raises(LookupError):
        await service.resolve_title("Definitely not a real title")
