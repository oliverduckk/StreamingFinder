from pathlib import Path

from app.db.database import SQLiteDatabase
from app.models.media import MediaFeatureProfile, RecommendationCandidate
from app.repositories.recommendation_feedback import RecommendationFeedbackRepository
from app.services.recommendation_feedback import (
    FeedbackTasteModel,
    build_feedback_taste_model,
    feedback_match_score,
    feedback_signal,
)
from app.services.recommendations import CandidateAccumulator, rank_candidates


def test_feedback_repository_aggregates_actions_and_summary(tmp_path: Path) -> None:
    repository = RecommendationFeedbackRepository(SQLiteDatabase(tmp_path / "feedback.db"))

    repository.record("movie", 1, "Candidate", "open_details")
    repository.record("movie", 1, "Candidate", "open_details")
    item = repository.record("movie", 1, "Candidate", "watchlist")
    repository.record("tv", 2, "Rejected", "not_interested")
    repository.record("tv", 3, "Already Seen", "watched")

    assert item.open_count == 2
    assert item.watchlist_count == 1
    assert item.last_action == "watchlist"
    assert feedback_signal(item) > 0

    summary = repository.summary()
    assert summary.titles_observed == 3
    assert summary.opened == 2
    assert summary.watchlisted == 1
    assert summary.watched == 1
    assert summary.not_interested == 1
    assert summary.positive_signal_titles == 1
    assert summary.negative_signal_titles == 1


def test_watched_feedback_is_neutral_by_itself(tmp_path: Path) -> None:
    repository = RecommendationFeedbackRepository(SQLiteDatabase(tmp_path / "feedback.db"))
    item = repository.record("movie", 44, "Seen", "watched")
    assert feedback_signal(item) == 0.0


def test_feedback_taste_model_learns_metadata_affinity(tmp_path: Path) -> None:
    repository = RecommendationFeedbackRepository(SQLiteDatabase(tmp_path / "feedback.db"))
    liked = repository.record("movie", 1, "Liked", "watchlist")
    disliked = repository.record("movie", 2, "Disliked", "not_interested")
    features = {
        ("movie", 1): MediaFeatureProfile(
            media_type="movie",
            tmdb_id=1,
            genre_ids=[53],
            genre_names=["Thriller"],
            keyword_ids=[999],
            keyword_names=["mystery"],
        ),
        ("movie", 2): MediaFeatureProfile(
            media_type="movie",
            tmdb_id=2,
            genre_ids=[10749],
            genre_names=["Romance"],
        ),
    }

    model = build_feedback_taste_model([liked, disliked], features)
    positive_score, positive_labels = feedback_match_score(model, features[("movie", 1)])
    negative_score, _ = feedback_match_score(model, features[("movie", 2)])

    assert positive_score > 0
    assert negative_score < 0
    assert "Thriller" in positive_labels or "mystery" in positive_labels


def test_rank_candidates_applies_feedback_score() -> None:
    candidate = RecommendationCandidate(
        tmdb_id=100,
        media_type="movie",
        title="Thriller Candidate",
        year=2025,
        vote_average=7.8,
        vote_count=5000,
        popularity=80.0,
        genre_ids=[53],
    )
    candidates = {
        ("movie", 100): CandidateAccumulator(
            candidate,
            7.8,
            5000,
            80.0,
            {},
            discovered=True,
        )
    }
    features = {
        ("movie", 100): MediaFeatureProfile(
            media_type="movie",
            tmdb_id=100,
            genre_ids=[53],
            genre_names=["Thriller"],
        )
    }

    positive = FeedbackTasteModel(
        genre_weights={53: 0.5},
        genre_names={53: "Thriller"},
        sample_size=4,
    )
    negative = FeedbackTasteModel(
        genre_weights={53: -0.5},
        genre_names={53: "Thriller"},
        sample_size=4,
    )

    positive_item = rank_candidates(
        candidates,
        {},
        features_by_key=features,
        feedback_model=positive,
        discovery_mode="familiar",
    )[0]
    negative_item = rank_candidates(
        candidates,
        {},
        features_by_key=features,
        feedback_model=negative,
        discovery_mode="familiar",
    )[0]

    assert positive_item.match_score > negative_item.match_score
    assert any("recommendation feedback" in reason for reason in positive_item.reasons)
