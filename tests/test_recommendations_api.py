from fastapi.testclient import TestClient

from app.api.dependencies import get_recommendation_service
from app.main import app
from app.models.media import RecommendationResponse


class FakeRecommendationService:
    async def recommend(
        self,
        *,
        media_type="all",
        limit=12,
        only_my_services=True,
        discovery_mode="balanced",
    ):
        return RecommendationResponse(
            media_filter=media_type,
            discovery_mode=discovery_mode,
            only_my_services=only_my_services,
            generated_from=4,
            total_considered=20,
            message="Test recommendations.",
            items=[],
        )


def test_recommendations_endpoint_exposes_filters() -> None:
    app.dependency_overrides[get_recommendation_service] = lambda: FakeRecommendationService()
    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/recommendations",
            params={
                "media_type": "movie",
                "limit": 6,
                "only_my_services": "false",
                "discovery_mode": "familiar",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["media_filter"] == "movie"
    assert payload["only_my_services"] is False
    assert payload["discovery_mode"] == "familiar"
    assert payload["generated_from"] == 4


def test_recommendations_endpoint_accepts_anime_filter() -> None:
    app.dependency_overrides[get_recommendation_service] = lambda: FakeRecommendationService()
    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/recommendations",
            params={"media_type": "anime", "limit": 5},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["media_filter"] == "anime"
