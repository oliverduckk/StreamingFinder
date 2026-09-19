import asyncio
from collections import defaultdict
from typing import Any

import httpx

from app.core.config import Settings
from app.models.media import (
    CountryAvailability,
    MediaAvailability,
    MediaFeatureProfile,
    MediaSearchResult,
    MediaType,
    RecommendationCandidate,
    StreamingServiceAvailability,
)
from app.services.streaming_services import get_service_for_provider_name


class TMDBClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.tmdb_base_url
        if settings.tmdb_read_access_token is None:
            raise ValueError("TMDB read access token is not configured.")
        self.token = settings.tmdb_read_access_token.get_secret_value()
        self._country_names: dict[str, str] | None = None
        self._country_names_lock = asyncio.Lock()

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

            title, year = extract_title_and_year(media_type, item)
            if not title:
                continue

            genre_ids = [
                genre_id
                for genre_id in item.get("genre_ids", [])
                if isinstance(genre_id, int)
            ]
            original_language = (
                item.get("original_language")
                if isinstance(item.get("original_language"), str)
                else None
            )
            results.append(
                MediaSearchResult(
                    tmdb_id=item["id"],
                    media_type=media_type,
                    title=title,
                    year=year,
                    overview=item.get("overview") or None,
                    poster_path=item.get("poster_path"),
                    genre_ids=genre_ids,
                    original_language=original_language,
                    is_anime=(original_language == "ja" and 16 in genre_ids),
                )
            )

        return results

    async def get_related_media(
        self,
        media_type: MediaType,
        tmdb_id: int,
    ) -> list[RecommendationCandidate]:
        """Return TMDB candidates related to a positively rated seed title.

        TMDB exposes a recommendation endpoint for movies and a documented
        similarity endpoint for TV series. Both return enough metadata for a
        first-pass local ranking.
        """
        path = (
            f"/movie/{tmdb_id}/recommendations"
            if media_type == "movie"
            else f"/tv/{tmdb_id}/similar"
        )
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=10.0,
        ) as client:
            response = await client.get(
                path,
                params={"language": "en-US", "page": 1},
            )
            response.raise_for_status()

        results: list[RecommendationCandidate] = []
        for item in response.json().get("results", []):
            title, year = extract_title_and_year(media_type, item)
            if not title or not isinstance(item.get("id"), int):
                continue
            results.append(
                RecommendationCandidate(
                    tmdb_id=item["id"],
                    media_type=media_type,
                    title=title,
                    year=year,
                    overview=item.get("overview") or None,
                    poster_path=item.get("poster_path"),
                    vote_average=float(item.get("vote_average") or 0.0),
                    vote_count=int(item.get("vote_count") or 0),
                    popularity=float(item.get("popularity") or 0.0),
                    genre_ids=[
                        genre_id
                        for genre_id in item.get("genre_ids", [])
                        if isinstance(genre_id, int)
                    ],
                    original_language=(
                        item.get("original_language")
                        if isinstance(item.get("original_language"), str)
                        else None
                    ),
                    is_anime=(
                        item.get("original_language") == "ja"
                        and 16 in item.get("genre_ids", [])
                    ),
                )
            )
        return results


    async def discover_media(
        self,
        media_type: MediaType,
        genre_ids: list[int],
        *,
        page: int = 1,
        original_language: str | None = None,
        required_genre_id: int | None = None,
        excluded_genre_ids: list[int] | None = None,
        minimum_vote_count: int | None = None,
        sort_by: str = "vote_average.desc",
    ) -> list[RecommendationCandidate]:
        """Return broader candidates from genres the local taste model prefers."""
        if not genre_ids and required_genre_id is None:
            return []
        params: dict[str, object] = {
            "language": "en-US",
            "page": max(1, int(page)),
            "sort_by": sort_by,
            "vote_count.gte": (
                minimum_vote_count
                if minimum_vote_count is not None
                else (350 if media_type == "movie" else 120)
            ),
        }
        if genre_ids:
            params["with_genres"] = "|".join(str(value) for value in genre_ids[:4])
        if required_genre_id is not None:
            other_genres = [value for value in genre_ids if value != required_genre_id][:4]
            params["with_genres"] = str(required_genre_id)
            if other_genres:
                params["with_genres"] += "," + "|".join(str(value) for value in other_genres)
        if excluded_genre_ids:
            params["without_genres"] = ",".join(str(value) for value in excluded_genre_ids)
        if original_language:
            params["with_original_language"] = original_language
        if media_type == "movie":
            params["include_adult"] = "false"
            params["include_video"] = "false"

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=10.0,
        ) as client:
            response = await client.get(f"/discover/{media_type}", params=params)
            response.raise_for_status()

        results: list[RecommendationCandidate] = []
        for item in response.json().get("results", []):
            title, year = extract_title_and_year(media_type, item)
            if not title or not isinstance(item.get("id"), int):
                continue
            results.append(
                RecommendationCandidate(
                    tmdb_id=item["id"],
                    media_type=media_type,
                    title=title,
                    year=year,
                    overview=item.get("overview") or None,
                    poster_path=item.get("poster_path"),
                    vote_average=float(item.get("vote_average") or 0.0),
                    vote_count=int(item.get("vote_count") or 0),
                    popularity=float(item.get("popularity") or 0.0),
                    genre_ids=[
                        genre_id
                        for genre_id in item.get("genre_ids", [])
                        if isinstance(genre_id, int)
                    ],
                    original_language=(
                        item.get("original_language")
                        if isinstance(item.get("original_language"), str)
                        else None
                    ),
                    is_anime=(
                        item.get("original_language") == "ja"
                        and 16 in item.get("genre_ids", [])
                    ),
                )
            )
        return results

    async def get_media_features(
        self,
        media_type: MediaType,
        tmdb_id: int,
    ) -> MediaFeatureProfile:
        """Fetch genres, keywords and creator/collection metadata for taste matching."""
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=10.0,
        ) as client:
            response = await client.get(
                f"/{media_type}/{tmdb_id}",
                params={
                    "language": "en-US",
                    "append_to_response": "keywords,credits",
                },
            )
            response.raise_for_status()
        payload = response.json()

        genres = payload.get("genres") or []
        genre_ids = [item["id"] for item in genres if isinstance(item.get("id"), int)]
        genre_names = [
            item["name"]
            for item in genres
            if isinstance(item.get("name"), str) and item["name"]
        ]

        keyword_payload = payload.get("keywords") or {}
        raw_keywords = (
            keyword_payload.get("keywords", [])
            if media_type == "movie"
            else keyword_payload.get("results", [])
        )
        keyword_ids = [
            item["id"]
            for item in raw_keywords
            if isinstance(item.get("id"), int)
        ]
        keyword_names = [
            item["name"]
            for item in raw_keywords
            if isinstance(item.get("name"), str) and item["name"]
        ]

        collection_id = None
        collection_name = None
        if media_type == "movie":
            collection = payload.get("belongs_to_collection") or {}
            if isinstance(collection.get("id"), int):
                collection_id = collection["id"]
            if isinstance(collection.get("name"), str):
                collection_name = collection["name"]

        creators: list[str] = []
        if media_type == "movie":
            credits = payload.get("credits") or {}
            for person in credits.get("crew", []):
                if person.get("job") != "Director":
                    continue
                name = person.get("name")
                if isinstance(name, str) and name and name not in creators:
                    creators.append(name)
        else:
            for person in payload.get("created_by") or []:
                name = person.get("name")
                if isinstance(name, str) and name and name not in creators:
                    creators.append(name)

        original_language = (
            payload.get("original_language")
            if isinstance(payload.get("original_language"), str)
            else None
        )
        is_anime = original_language == "ja" and 16 in genre_ids

        return MediaFeatureProfile(
            media_type=media_type,
            tmdb_id=tmdb_id,
            genre_ids=genre_ids,
            genre_names=genre_names,
            keyword_ids=keyword_ids,
            keyword_names=keyword_names,
            collection_id=collection_id,
            collection_name=collection_name,
            creators=creators[:4],
            original_language=original_language,
            is_anime=is_anime,
        )

    async def get_subscription_providers(
        self,
        media_type: MediaType,
        tmdb_id: int,
        service_keys: set[str] | None = None,
    ) -> list[StreamingServiceAvailability]:
        """Return service-first subscription availability without refetching details."""
        country_names = await self._get_country_names()
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=10.0,
        ) as client:
            response = await client.get(f"/{media_type}/{tmdb_id}/watch/providers")
            response.raise_for_status()

        return group_subscription_providers(
            response.json().get("results", {}),
            service_keys=service_keys,
            country_names=country_names,
        )

    async def _get_country_names(self) -> dict[str, str]:
        if self._country_names is not None:
            return self._country_names
        async with self._country_names_lock:
            if self._country_names is not None:
                return self._country_names
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                timeout=10.0,
            ) as client:
                response = await client.get(
                    "/configuration/countries",
                    params={"language": "en-US"},
                )
                response.raise_for_status()
            self._country_names = build_country_name_map(response.json())
        return self._country_names

    async def get_subscription_availability(
        self,
        media_type: MediaType,
        tmdb_id: int,
        service_keys: set[str] | None = None,
    ) -> MediaAvailability:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=10.0,
        ) as client:
            details_response, providers_response = await asyncio.gather(
                client.get(
                    f"/{media_type}/{tmdb_id}",
                    params={"language": "en-US"},
                ),
                client.get(f"/{media_type}/{tmdb_id}/watch/providers"),
            )

            details_response.raise_for_status()
            providers_response.raise_for_status()

        country_names = await self._get_country_names()

        details = details_response.json()
        title, year = extract_title_and_year(media_type, details)
        if not title:
            title = f"TMDB {media_type} {tmdb_id}"

        providers = group_subscription_providers(
            providers_response.json().get("results", {}),
            service_keys=service_keys,
            country_names=country_names,
        )

        return MediaAvailability(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            year=year,
            overview=details.get("overview") or None,
            poster_path=details.get("poster_path"),
            providers=providers,
        )


def extract_title_and_year(
    media_type: MediaType,
    payload: dict[str, Any],
) -> tuple[str | None, int | None]:
    if media_type == "movie":
        title = payload.get("title")
        date_value = payload.get("release_date")
    else:
        title = payload.get("name")
        date_value = payload.get("first_air_date")

    year = None
    if isinstance(date_value, str) and len(date_value) >= 4 and date_value[:4].isdigit():
        year = int(date_value[:4])

    return title, year


def build_country_name_map(countries: list[dict[str, Any]]) -> dict[str, str]:
    """Map TMDB ISO country codes to human-readable English names."""
    country_names: dict[str, str] = {}

    for country in countries:
        code = country.get("iso_3166_1")
        name = country.get("english_name") or country.get("native_name")
        if isinstance(code, str) and code and isinstance(name, str) and name:
            country_names[code] = name

    return country_names


def group_subscription_providers(
    regional_results: dict[str, dict],
    service_keys: set[str] | None = None,
    country_names: dict[str, str] | None = None,
) -> list[StreamingServiceAvailability]:
    """Convert TMDB country-first flatrate data into service-first availability.

    Known consumer services are canonicalised so duplicate TMDB provider records
    collapse into one result. Unknown providers are preserved when no service
    filter is requested.
    """
    country_names = country_names or {}
    group_countries: dict[str, set[str]] = defaultdict(set)
    group_provider_ids: dict[str, set[int]] = defaultdict(set)
    group_metadata: dict[str, tuple[str, str | None]] = {}

    for country_code, availability in regional_results.items():
        for provider in availability.get("flatrate", []):
            provider_id = provider.get("provider_id")
            provider_name = provider.get("provider_name")

            if not isinstance(provider_id, int) or not provider_name:
                continue

            known_service = get_service_for_provider_name(provider_name)

            if service_keys is not None:
                if known_service is None or known_service.key not in service_keys:
                    continue

            if known_service is not None:
                group_key = known_service.key
                display_name = known_service.name
            else:
                group_key = f"tmdb_{provider_id}"
                display_name = provider_name

            group_countries[group_key].add(country_code)
            group_provider_ids[group_key].add(provider_id)

            existing_name, existing_logo = group_metadata.get(
                group_key,
                (display_name, None),
            )
            group_metadata[group_key] = (
                existing_name,
                existing_logo or provider.get("logo_path"),
            )

    grouped = [
        StreamingServiceAvailability(
            service_key=group_key,
            service_name=group_metadata[group_key][0],
            provider_ids=sorted(group_provider_ids[group_key]),
            logo_path=group_metadata[group_key][1],
            countries=sorted(
                (
                    CountryAvailability(
                        code=country_code,
                        name=country_names.get(country_code, country_code),
                    )
                    for country_code in countries
                ),
                key=lambda country: (country.name.casefold(), country.code),
            ),
        )
        for group_key, countries in group_countries.items()
    ]

    return sorted(grouped, key=lambda provider: provider.service_name.casefold())
