from __future__ import annotations

import json

from app.db.database import SQLiteDatabase
from app.models.media import MediaFeatureProfile, MediaType


class MediaFeatureRepository:
    """Persist TMDB metadata used by the taste model and recommender."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get(self, media_type: MediaType, tmdb_id: int) -> MediaFeatureProfile | None:
        self.database.initialise()
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT media_type, tmdb_id, genre_ids_json, genre_names_json,
                       keyword_ids_json, keyword_names_json, collection_id,
                       collection_name, creators_json, original_language, is_anime
                FROM media_feature_cache
                WHERE media_type = ? AND tmdb_id = ?
                """,
                (media_type, tmdb_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_profile(row)

    def upsert(self, profile: MediaFeatureProfile) -> MediaFeatureProfile:
        self.database.initialise()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO media_feature_cache (
                    media_type, tmdb_id, genre_ids_json, genre_names_json,
                    keyword_ids_json, keyword_names_json, collection_id,
                    collection_name, creators_json, original_language, is_anime,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(media_type, tmdb_id) DO UPDATE SET
                    genre_ids_json = excluded.genre_ids_json,
                    genre_names_json = excluded.genre_names_json,
                    keyword_ids_json = excluded.keyword_ids_json,
                    keyword_names_json = excluded.keyword_names_json,
                    collection_id = excluded.collection_id,
                    collection_name = excluded.collection_name,
                    creators_json = excluded.creators_json,
                    original_language = excluded.original_language,
                    is_anime = excluded.is_anime,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    profile.media_type,
                    profile.tmdb_id,
                    json.dumps(profile.genre_ids),
                    json.dumps(profile.genre_names),
                    json.dumps(profile.keyword_ids),
                    json.dumps(profile.keyword_names),
                    profile.collection_id,
                    profile.collection_name,
                    json.dumps(profile.creators),
                    profile.original_language,
                    1 if profile.is_anime else 0,
                ),
            )
        return profile

    @staticmethod
    def _row_to_profile(row) -> MediaFeatureProfile:
        return MediaFeatureProfile(
            media_type=row["media_type"],
            tmdb_id=row["tmdb_id"],
            genre_ids=json.loads(row["genre_ids_json"] or "[]"),
            genre_names=json.loads(row["genre_names_json"] or "[]"),
            keyword_ids=json.loads(row["keyword_ids_json"] or "[]"),
            keyword_names=json.loads(row["keyword_names_json"] or "[]"),
            collection_id=row["collection_id"],
            collection_name=row["collection_name"],
            creators=json.loads(row["creators_json"] or "[]"),
            original_language=row["original_language"],
            is_anime=bool(row["is_anime"]),
        )
