from pathlib import Path

import pytest

from app.db.database import SQLiteDatabase
from app.models.media import (
    CountryAvailability,
    MediaLibraryEntry,
    MediaRating,
    MediaSearchResult,
    RatingCategoryScore,
    RecommendationCandidate,
    StreamingServiceAvailability,
)
from app.repositories.library import MediaLibraryRepository
from app.repositories.preferences import StreamingPreferencesRepository
from app.repositories.ratings import MediaRatingRepository
from app.services.recommendations import (
    CandidateAccumulator,
    RecommendationSeed,
    RecommendationService,
    rank_candidates,
    select_recommendation_seeds,
)
from app.services.rating_system import RATING_CATEGORIES


def _rating(media_type: str, tmdb_id: int, title: str, totalish: float, enjoyment: float) -> MediaRating:
    base = max(0.0, min(10.0, totalish / 10.0))
    categories = [
        RatingCategoryScore(
            key=category.key,
            label=category.label,
            score=enjoyment if category.key == "enjoyment" else base,
        )
        for category in RATING_CATEGORIES
    ]
    return MediaRating(
        media_type=media_type,
        tmdb_id=tmdb_id,
        title=title,
        year=2000,
        categories=categories,
        total=round(sum(item.score for item in categories), 1),
        notes=None,
        created_at="2026-01-01 00:00:00",
        updated_at="2026-01-01 00:00:00",
    )


def _entry(media_type: str, tmdb_id: int, title: str, *, status: str = "watched", favourite: bool = False) -> MediaLibraryEntry:
    return MediaLibraryEntry(
        media_type=media_type,
        tmdb_id=tmdb_id,
        title=title,
        year=2000,
        overview=None,
        poster_path=None,
        status=status,
        favourite=favourite,
        created_at="2026-01-01 00:00:00",
        updated_at="2026-01-01 00:00:00",
    )


def test_seed_selection_prefers_favourites_and_excludes_disliked_titles() -> None:
    ratings = [
        _rating("movie", 1, "Favourite", 95, 10),
        _rating("movie", 2, "Good", 85, 8.5),
        _rating("movie", 3, "Bad", 40, 4),
    ]
    entries = [
        _entry("movie", 1, "Favourite", favourite=True),
        _entry("movie", 2, "Good"),
        _entry("movie", 3, "Bad"),
    ]

    seeds = select_recommendation_seeds(ratings, entries)

    assert [seed.tmdb_id for seed in seeds] == [1, 2]
    assert seeds[0].favourite is True
    assert seeds[0].weight > seeds[1].weight


def test_rank_candidates_rewards_consensus_and_excludes_watched() -> None:
    seed_a = RecommendationSeed("movie", 1, "A", 95.0, True, 9.5, 1.1)
    seed_b = RecommendationSeed("movie", 2, "B", 90.0, False, 9.0, 0.9)
    consensus_media = RecommendationCandidate(
        tmdb_id=10,
        media_type="movie",
        title="Consensus",
        year=2020,
        vote_average=8.0,
        vote_count=5000,
    )
    single_media = RecommendationCandidate(
        tmdb_id=11,
        media_type="movie",
        title="Single",
        year=2021,
        vote_average=8.0,
        vote_count=5000,
    )
    watched_media = RecommendationCandidate(
        tmdb_id=12,
        media_type="movie",
        title="Watched",
        year=2022,
        vote_average=9.0,
        vote_count=9000,
    )
    candidates = {
        ("movie", 10): CandidateAccumulator(consensus_media, 8.0, 5000, 50.0, {("movie", 1): seed_a, ("movie", 2): seed_b}),
        ("movie", 11): CandidateAccumulator(single_media, 8.0, 5000, 50.0, {("movie", 1): seed_a}),
        ("movie", 12): CandidateAccumulator(watched_media, 9.0, 9000, 70.0, {("movie", 1): seed_a, ("movie", 2): seed_b}),
    }
    library = {("movie", 12): _entry("movie", 12, "Watched", status="watched")}

    ranked = rank_candidates(candidates, library)

    assert [item.tmdb_id for item in ranked] == [10, 11]
    assert ranked[0].match_score > ranked[1].match_score
    assert "2 of your highly rated titles" in ranked[0].reasons[0]


class FakeTMDB:
    async def get_related_media(self, media_type: str, tmdb_id: int):
        return [
            RecommendationCandidate(
                tmdb_id=100,
                media_type=media_type,
                title="Candidate",
                year=2024,
                overview="A candidate",
                poster_path="/poster.jpg",
                vote_average=8.4,
                vote_count=4000,
                popularity=100.0,
            )
        ]

    async def get_subscription_providers(self, media_type: str, tmdb_id: int, service_keys=None):
        return [
            StreamingServiceAvailability(
                service_key="netflix",
                service_name="Netflix",
                provider_ids=[8],
                logo_path=None,
                countries=[CountryAvailability(code="JP", name="Japan")],
            )
        ]


@pytest.mark.anyio
async def test_recommendation_service_filters_to_selected_services(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "recommendations.db")
    library = MediaLibraryRepository(database)
    ratings = MediaRatingRepository(database)
    preferences = StreamingPreferencesRepository(database)
    preferences.set_enabled_services({"netflix"})

    media = MediaSearchResult(tmdb_id=1, media_type="movie", title="Seed", year=2020)
    library.upsert(media, "watched", favourite=True)
    ratings.upsert(
        "movie",
        1,
        {category.key: 9.0 for category in RATING_CATEGORIES},
        notes=None,
    )

    service = RecommendationService(FakeTMDB(), library, ratings, preferences)
    response = await service.recommend(limit=5, only_my_services=True)

    assert len(response.items) == 1
    assert response.items[0].title == "Candidate"
    assert response.items[0].providers[0].service_name == "Netflix"
    assert "Available on Netflix" in response.items[0].reasons[-1]


def test_negative_signal_selection_uses_low_scores_and_enjoyment() -> None:
    from app.services.recommendations import select_negative_signals

    ratings = [
        _rating("movie", 1, "Loved", 92, 9.5),
        _rating("movie", 2, "Mediocre", 62, 5.5),
        _rating("movie", 3, "Hated", 35, 3.0),
    ]
    entries = [
        _entry("movie", 1, "Loved"),
        _entry("movie", 2, "Mediocre"),
        _entry("movie", 3, "Hated"),
    ]

    signals = select_negative_signals(ratings, entries)

    assert [signal.tmdb_id for signal in signals] == [3, 2]
    assert signals[0].weight > signals[1].weight


def test_feature_taste_model_can_penalise_disliked_genres() -> None:
    from app.models.media import MediaFeatureProfile
    from app.services.recommendations import build_feature_taste_model

    liked = MediaFeatureProfile(
        media_type="movie",
        tmdb_id=1,
        genre_ids=[878],
        genre_names=["Science Fiction"],
    )
    disliked = MediaFeatureProfile(
        media_type="movie",
        tmdb_id=2,
        genre_ids=[10749],
        genre_names=["Romance"],
    )

    model = build_feature_taste_model([(1.0, liked), (-0.8, disliked)])

    assert model.genre_weights[878] > 0
    assert model.genre_weights[10749] < 0
    assert model.top_positive_genres() == [878]


def test_diversity_prevents_one_collection_from_filling_top_slots() -> None:
    from app.models.media import RecommendationItem
    from app.services.recommendations import diversify_recommendations

    def item(tmdb_id: int, title: str, score: float, collection_id: int | None):
        return RecommendationItem(
            media_type="movie",
            tmdb_id=tmdb_id,
            title=title,
            match_score=score,
            tmdb_vote_average=8.0,
            tmdb_vote_count=5000,
            seed_titles=[],
            reasons=[],
            genre_names=["Fantasy", "Adventure"],
            collection_id=collection_id,
            providers=[],
        )

    ranked = [
        item(1, "Franchise One", 95.0, 100),
        item(2, "Franchise Two", 94.0, 100),
        item(3, "Different Film", 89.0, 200),
    ]

    diversified = diversify_recommendations(ranked, limit=3)

    assert [entry.tmdb_id for entry in diversified[:2]] == [1, 3]


def test_seed_diversity_avoids_multiple_titles_from_same_collection() -> None:
    from app.models.media import MediaFeatureProfile
    from app.services.recommendations import diversify_recommendation_seeds

    seeds = [
        RecommendationSeed("movie", 1, "Part One", 99.0, True, 10.0, 1.1),
        RecommendationSeed("movie", 2, "Part Two", 98.0, True, 10.0, 1.0),
        RecommendationSeed("movie", 3, "Different", 90.0, True, 9.0, 0.9),
    ]
    features = {
        ("movie", 1): MediaFeatureProfile(
            media_type="movie", tmdb_id=1, collection_id=50
        ),
        ("movie", 2): MediaFeatureProfile(
            media_type="movie", tmdb_id=2, collection_id=50
        ),
        ("movie", 3): MediaFeatureProfile(
            media_type="movie", tmdb_id=3, collection_id=60
        ),
    }

    diversified = diversify_recommendation_seeds(seeds, features, limit=2)

    assert [seed.tmdb_id for seed in diversified] == [1, 3]


def test_live_action_tv_filter_excludes_animation_and_anime_mode_keeps_japanese_animation() -> None:
    from app.services.recommendations import _candidate_matches_filter

    live_action = RecommendationCandidate(
        tmdb_id=201,
        media_type="tv",
        title="Live Action",
        vote_count=1000,
        genre_ids=[18, 80],
        original_language="en",
    )
    anime = RecommendationCandidate(
        tmdb_id=202,
        media_type="tv",
        title="Anime",
        vote_count=1000,
        genre_ids=[16, 18],
        original_language="ja",
    )
    western_animation = RecommendationCandidate(
        tmdb_id=203,
        media_type="tv",
        title="Western Animation",
        vote_count=1000,
        genre_ids=[16, 35],
        original_language="en",
    )

    assert _candidate_matches_filter(live_action, "tv") is True
    assert _candidate_matches_filter(anime, "tv") is False
    assert _candidate_matches_filter(anime, "anime") is True
    assert _candidate_matches_filter(western_animation, "anime") is False


def test_tv_quality_gate_suppresses_thin_single_seed_candidates() -> None:
    from app.services.recommendations import _passes_candidate_quality_gate

    obscure = RecommendationCandidate(
        tmdb_id=301,
        media_type="tv",
        title="Obscure",
        vote_count=40,
        genre_ids=[18],
        original_language="en",
    )

    assert _passes_candidate_quality_gate(obscure, 1, "tv") is False
    assert _passes_candidate_quality_gate(obscure, 2, "tv") is False
    assert _passes_candidate_quality_gate(obscure, 2, "tv", "hidden") is True


def test_familiar_mode_requires_more_audience_confidence_than_balanced() -> None:
    from app.services.recommendations import _passes_candidate_quality_gate

    candidate = RecommendationCandidate(
        tmdb_id=401,
        media_type="tv",
        title="Mid-size Show",
        vote_count=300,
        genre_ids=[18, 80],
        original_language="en",
    )

    assert _passes_candidate_quality_gate(candidate, 1, "tv", "balanced") is True
    assert _passes_candidate_quality_gate(candidate, 1, "tv", "familiar") is False
