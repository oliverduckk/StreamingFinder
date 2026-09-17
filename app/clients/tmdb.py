import httpx

from app.core.config import Settings
from app.models.media import MediaSearchResult


class TMDBClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.tmdb_base_url
        if settings.tmdb_read_access_token is None:
            raise ValueError("TMDB read access token is not configured.")
        self.token = settings.tmdb_read_access_token.get_secret_value()

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    async def search_media(self, query: str) -> list[MediaSearchResult]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=10.0,
        ) as client:
            response = await client.get(
                "/search/multi",
                params={
                    "query": query,
                    "include_adult": "false",
                    "language": "en-US",
                    "page": 1,
                },
            )
            response.raise_for_status()

        results: list[MediaSearchResult] = []
        for item in response.json().get("results", []):
            media_type = item.get("media_type")
            if media_type not in {"movie", "tv"}:
                continue

            title = item.get("title") if media_type == "movie" else item.get("name")
            date_value = (
                item.get("release_date")
                if media_type == "movie"
                else item.get("first_air_date")
            )

            year = None
            if date_value and len(date_value) >= 4 and date_value[:4].isdigit():
                year = int(date_value[:4])

            if not title:
                continue

            results.append(
                MediaSearchResult(
                    tmdb_id=item["id"],
                    media_type=media_type,
                    title=title,
                    year=year,
                    overview=item.get("overview") or None,
                    poster_path=item.get("poster_path"),
                )
            )

        return results
