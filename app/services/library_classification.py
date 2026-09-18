from __future__ import annotations

import asyncio

from app.clients.tmdb import TMDBClient
from app.models.media import MediaLibraryEntry
from app.repositories.library import MediaLibraryRepository


class LibraryClassificationService:
    """Backfill lightweight media classification used by Library filters.

    New search results already carry enough TMDB metadata to classify anime.
    Older library rows predate that metadata, so this service lazily enriches
    only the unknown rows once and persists the result in SQLite.
    """

    def __init__(self, tmdb: TMDBClient, library: MediaLibraryRepository) -> None:
        self.tmdb = tmdb
        self.library = library

    async def backfill_unknown(self, entries: list[MediaLibraryEntry]) -> int:
        unknown = [entry for entry in entries if entry.is_anime is None]
        if not unknown:
            return 0

        semaphore = asyncio.Semaphore(6)

        async def classify(entry: MediaLibraryEntry) -> bool:
            try:
                async with semaphore:
                    feature = await self.tmdb.get_media_features(
                        entry.media_type,
                        entry.tmdb_id,
                    )
            except Exception:
                return False
            self.library.set_is_anime(
                entry.media_type,
                entry.tmdb_id,
                feature.is_anime,
            )
            return True

        results = await asyncio.gather(*(classify(entry) for entry in unknown))
        return sum(1 for result in results if result)
