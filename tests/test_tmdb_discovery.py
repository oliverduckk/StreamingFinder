import pytest

from app.clients.tmdb import TMDBClient
from app.core.config import Settings


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {
            "results": [
                {
                    "id": 9001,
                    "name": "Broad Anime",
                    "first_air_date": "2024-01-01",
                    "overview": "",
                    "poster_path": None,
                    "vote_average": 8.0,
                    "vote_count": 1200,
                    "popularity": 100.0,
                    "genre_ids": [16, 18],
                    "original_language": "ja",
                }
            ]
        }


class FakeAsyncClient:
    last_params = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, path: str, params=None):
        type(self).last_params = params
        return FakeResponse()


@pytest.mark.anyio
async def test_discover_media_allows_broad_required_genre_query(monkeypatch) -> None:
    monkeypatch.setattr("app.clients.tmdb.httpx.AsyncClient", FakeAsyncClient)
    client = TMDBClient(Settings(tmdb_read_access_token="test-token"))

    results = await client.discover_media(
        "tv",
        [],
        original_language="ja",
        required_genre_id=16,
        minimum_vote_count=250,
        sort_by="popularity.desc",
    )

    assert len(results) == 1
    assert results[0].title == "Broad Anime"
    assert FakeAsyncClient.last_params["with_genres"] == "16"
    assert FakeAsyncClient.last_params["with_original_language"] == "ja"
    assert FakeAsyncClient.last_params["vote_count.gte"] == 250
