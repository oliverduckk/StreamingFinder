from fastapi.testclient import TestClient

from app.api.dependencies import get_assistant_service
from app.main import app
from app.models.assistant import AssistantTitleResolution, AssistantWhereToWatchResponse
from app.models.media import MediaAvailability, MediaSearchResult


class FakeAssistantService:
    async def where_to_watch(
        self,
        query,
        *,
        media_type=None,
        year=None,
        only_my_services=True,
    ):
        selected = MediaSearchResult(
            tmdb_id=157336,
            media_type="movie",
            title="Interstellar",
            year=2014,
        )
        return AssistantWhereToWatchResponse(
            resolution=AssistantTitleResolution(
                query=query,
                selected=selected,
                exact_title_match=True,
            ),
            only_my_services=only_my_services,
            services_considered=["netflix"],
            availability=MediaAvailability(
                tmdb_id=157336,
                media_type="movie",
                title="Interstellar",
                year=2014,
                providers=[],
            ),
        )


def test_assistant_where_to_watch_route() -> None:
    app.dependency_overrides[get_assistant_service] = lambda: FakeAssistantService()
    try:
        client = TestClient(app)
        response = client.get("/api/v1/assistant/where-to-watch?query=Interstellar")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolution"]["selected"]["title"] == "Interstellar"
    assert payload["resolution"]["exact_title_match"] is True
    assert payload["services_considered"] == ["netflix"]
