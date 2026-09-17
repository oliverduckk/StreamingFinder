from fastapi.testclient import TestClient

from app.api.dependencies import get_preferences_repository, get_tmdb_client
from app.db.database import SQLiteDatabase
from app.main import app
from app.models.media import MediaAvailability
from app.repositories.preferences import StreamingPreferencesRepository


def test_preferences_persist_in_sqlite(tmp_path) -> None:
    database_path = tmp_path / "streaming_finder.db"

    first_repository = StreamingPreferencesRepository(SQLiteDatabase(database_path))
    first_repository.set_enabled_services({"prime_video", "netflix"})

    second_repository = StreamingPreferencesRepository(SQLiteDatabase(database_path))

    assert second_repository.get_enabled_services() == ["netflix", "prime_video"]


def test_preferences_api_can_save_and_retrieve_services(tmp_path) -> None:
    repository = StreamingPreferencesRepository(SQLiteDatabase(tmp_path / "preferences.db"))
    app.dependency_overrides[get_preferences_repository] = lambda: repository

    try:
        client = TestClient(app)

        update_response = client.put(
            "/api/v1/preferences/services",
            json={"services": ["prime_video", "netflix"]},
        )
        get_response = client.get("/api/v1/preferences/services")

        assert update_response.status_code == 200
        assert update_response.json() == {"services": ["netflix", "prime_video"]}
        assert get_response.json() == {"services": ["netflix", "prime_video"]}
    finally:
        app.dependency_overrides.clear()


def test_preferences_api_rejects_unknown_service(tmp_path) -> None:
    repository = StreamingPreferencesRepository(SQLiteDatabase(tmp_path / "preferences.db"))
    app.dependency_overrides[get_preferences_repository] = lambda: repository

    try:
        client = TestClient(app)
        response = client.put(
            "/api/v1/preferences/services",
            json={"services": ["netflix", "made_up_service"]},
        )

        assert response.status_code == 400
        assert "made_up_service" in response.json()["detail"]
        assert repository.get_enabled_services() == []
    finally:
        app.dependency_overrides.clear()


class FakeTMDBClient:
    def __init__(self) -> None:
        self.received_service_keys: set[str] | None = None

    async def get_subscription_availability(
        self,
        media_type,
        tmdb_id,
        service_keys=None,
    ) -> MediaAvailability:
        self.received_service_keys = service_keys
        return MediaAvailability(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title="Interstellar",
            year=2014,
            providers=[],
        )


def test_availability_can_use_saved_my_services(tmp_path) -> None:
    repository = StreamingPreferencesRepository(SQLiteDatabase(tmp_path / "preferences.db"))
    repository.set_enabled_services({"netflix", "prime_video"})
    fake_tmdb = FakeTMDBClient()

    app.dependency_overrides[get_preferences_repository] = lambda: repository
    app.dependency_overrides[get_tmdb_client] = lambda: fake_tmdb

    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/availability/movie/157336?my_services=true"
        )

        assert response.status_code == 200
        assert fake_tmdb.received_service_keys == {"netflix", "prime_video"}
    finally:
        app.dependency_overrides.clear()


def test_availability_rejects_explicit_and_saved_filters_together(tmp_path) -> None:
    repository = StreamingPreferencesRepository(SQLiteDatabase(tmp_path / "preferences.db"))
    fake_tmdb = FakeTMDBClient()

    app.dependency_overrides[get_preferences_repository] = lambda: repository
    app.dependency_overrides[get_tmdb_client] = lambda: fake_tmdb

    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/availability/movie/157336"
            "?services=netflix&my_services=true"
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Use either services or my_services, not both."
    finally:
        app.dependency_overrides.clear()
