from pathlib import Path

from fastapi.testclient import TestClient

from app.api.dependencies import get_recommendation_feedback_repository
from app.db.database import SQLiteDatabase
from app.main import app
from app.repositories.recommendation_feedback import RecommendationFeedbackRepository


def test_recommendation_feedback_api_records_and_summarises(tmp_path: Path) -> None:
    repository = RecommendationFeedbackRepository(SQLiteDatabase(tmp_path / "feedback.db"))
    app.dependency_overrides[get_recommendation_feedback_repository] = lambda: repository
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/recommendation-feedback/movie/157336",
            json={"title": "Interstellar", "action": "open_details"},
        )
        assert response.status_code == 200
        assert response.json()["open_count"] == 1

        response = client.post(
            "/api/v1/recommendation-feedback/movie/157336",
            json={"title": "Interstellar", "action": "watchlist"},
        )
        assert response.status_code == 200
        assert response.json()["watchlist_count"] == 1

        summary = client.get("/api/v1/recommendation-feedback/summary")
        assert summary.status_code == 200
        assert summary.json()["titles_observed"] == 1
        assert summary.json()["positive_signal_titles"] == 1
    finally:
        app.dependency_overrides.clear()
