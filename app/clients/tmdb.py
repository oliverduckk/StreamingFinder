import asyncio
from collections import defaultdict
from typing import Any

import httpx

from app.core.config import Settings
from app.models.media import (
    CountryAvailability,
    MediaAvailability,
    MediaSearchResult,
    MediaType,
    StreamingServiceAvailability,
)
from app.services.streaming_services import get_service_for_provider_name


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

            title, year = extract_title_and_year(media_type, item)
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
            details_response, providers_response, countries_response = await asyncio.gather(
                client.get(
                    f"/{media_type}/{tmdb_id}",
                    params={"language": "en-US"},
                ),
                client.get(f"/{media_type}/{tmdb_id}/watch/providers"),
                client.get(
                    "/configuration/countries",
                    params={"language": "en-US"},
                ),
            )

        details_response.raise_for_status()
        providers_response.raise_for_status()
        countries_response.raise_for_status()

        details = details_response.json()
        title, year = extract_title_and_year(media_type, details)
        if not title:
            title = f"TMDB {media_type} {tmdb_id}"

        country_names = build_country_name_map(countries_response.json())
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
