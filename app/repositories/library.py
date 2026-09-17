from app.db.database import SQLiteDatabase
from app.models.media import LibraryStatus, MediaLibraryEntry, MediaSearchResult, MediaType


class MediaLibraryRepository:
    """Persist the user's personal movie/TV library."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get(self, media_type: MediaType, tmdb_id: int) -> MediaLibraryEntry | None:
        self.database.initialise()
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT media_type, tmdb_id, title, year, overview, poster_path,
                       status, favourite, created_at, updated_at
                FROM media_library
                WHERE media_type = ? AND tmdb_id = ?
                """,
                (media_type, tmdb_id),
            ).fetchone()

        return self._row_to_entry(row) if row is not None else None

    def list(
        self,
        *,
        status: LibraryStatus | None = None,
        favourite: bool | None = None,
    ) -> list[MediaLibraryEntry]:
        self.database.initialise()
        clauses: list[str] = []
        values: list[object] = []

        if status is not None:
            clauses.append("status = ?")
            values.append(status)
        if favourite is not None:
            clauses.append("favourite = ?")
            values.append(1 if favourite else 0)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT media_type, tmdb_id, title, year, overview, poster_path,
                       status, favourite, created_at, updated_at
                FROM media_library
                {where}
                ORDER BY updated_at DESC, title COLLATE NOCASE ASC
                """,
                values,
            ).fetchall()

        return [self._row_to_entry(row) for row in rows]

    def upsert(
        self,
        media: MediaSearchResult,
        status: LibraryStatus,
        *,
        favourite: bool | None = None,
    ) -> MediaLibraryEntry:
        self.database.initialise()
        existing = self.get(media.media_type, media.tmdb_id)
        favourite_value = existing.favourite if existing and favourite is None else bool(favourite)

        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO media_library (
                    media_type, tmdb_id, title, year, overview, poster_path,
                    status, favourite, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(media_type, tmdb_id) DO UPDATE SET
                    title = excluded.title,
                    year = excluded.year,
                    overview = excluded.overview,
                    poster_path = excluded.poster_path,
                    status = excluded.status,
                    favourite = excluded.favourite,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    media.media_type,
                    media.tmdb_id,
                    media.title,
                    media.year,
                    media.overview,
                    media.poster_path,
                    status,
                    1 if favourite_value else 0,
                ),
            )

        entry = self.get(media.media_type, media.tmdb_id)
        if entry is None:  # pragma: no cover - defensive database boundary.
            raise RuntimeError("Media library entry was not saved.")
        return entry

    def set_favourite(
        self,
        media_type: MediaType,
        tmdb_id: int,
        favourite: bool,
    ) -> MediaLibraryEntry | None:
        self.database.initialise()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE media_library
                SET favourite = ?, updated_at = CURRENT_TIMESTAMP
                WHERE media_type = ? AND tmdb_id = ?
                """,
                (1 if favourite else 0, media_type, tmdb_id),
            )
        return self.get(media_type, tmdb_id)

    def remove(self, media_type: MediaType, tmdb_id: int) -> bool:
        self.database.initialise()
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM media_library WHERE media_type = ? AND tmdb_id = ?",
                (media_type, tmdb_id),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_entry(row) -> MediaLibraryEntry:
        return MediaLibraryEntry(
            media_type=row["media_type"],
            tmdb_id=row["tmdb_id"],
            title=row["title"],
            year=row["year"],
            overview=row["overview"],
            poster_path=row["poster_path"],
            status=row["status"],
            favourite=bool(row["favourite"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
