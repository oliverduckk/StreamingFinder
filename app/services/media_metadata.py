from __future__ import annotations

import asyncio
from collections.abc import Iterable

from app.clients.tmdb import TMDBClient
from app.models.media import MediaFeatureProfile, MediaType
from app.repositories.features import MediaFeatureRepository


class MediaMetadataService:
    """Fetch TMDB feature metadata once, then reuse it from SQLite."""

    def __init__(self, tmdb: TMDBClient, repository: MediaFeatureRepository) -> None:
        self.tmdb = tmdb
        self.repository = repository
        self._memory_cache: dict[tuple[str, int], MediaFeatureProfile] = {}

    async def get(self, media_type: MediaType, tmdb_id: int) -> MediaFeatureProfile:
        key = (media_type, tmdb_id)
        if key in self._memory_cache:
            return self._memory_cache[key]

        cached = self.repository.get(media_type, tmdb_id)
        if cached is not None:
            self._memory_cache[key] = cached
            return cached

        profile = await self.tmdb.get_media_features(media_type, tmdb_id)
        self.repository.upsert(profile)
        self._memory_cache[key] = profile
        return profile

    async def get_many(
        self,
        keys: Iterable[tuple[MediaType, int]],
        *,
        concurrency: int = 6,
    ) -> dict[tuple[str, int], MediaFeatureProfile]:
        unique = list(dict.fromkeys(keys))
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def fetch(key: tuple[MediaType, int]):
            async with semaphore:
                try:
                    return key, await self.get(*key)
                except Exception:
                    return key, None

        results = await asyncio.gather(*(fetch(key) for key in unique))
        return {
            key: profile
            for key, profile in results
            if profile is not None
        }
