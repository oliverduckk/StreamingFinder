from app.db.database import SQLiteDatabase
from app.models.media import MediaType, RecommendationDismissal


class RecommendationDismissalRepository:
    """Persist titles the user does not want recommendation cards to show again."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def list(self) -> list[RecommendationDismissal]:
        self.database.initialise()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT media_type, tmdb_id, title, created_at
                FROM recommendation_dismissals
                ORDER BY created_at DESC, title COLLATE NOCASE ASC
                """
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def contains(self, media_type: MediaType, tmdb_id: int) -> bool:
        self.database.initialise()
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM recommendation_dismissals
                WHERE media_type = ? AND tmdb_id = ?
                """,
                (media_type, tmdb_id),
            ).fetchone()
        return row is not None

    def add(
        self,
        media_type: MediaType,
        tmdb_id: int,
        title: str,
    ) -> RecommendationDismissal:
        self.database.initialise()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO recommendation_dismissals (media_type, tmdb_id, title)
                VALUES (?, ?, ?)
                ON CONFLICT(media_type, tmdb_id) DO UPDATE SET
                    title = excluded.title,
                    created_at = CURRENT_TIMESTAMP
                """,
                (media_type, tmdb_id, title),
            )
            row = connection.execute(
                """
                SELECT media_type, tmdb_id, title, created_at
                FROM recommendation_dismissals
                WHERE media_type = ? AND tmdb_id = ?
                """,
                (media_type, tmdb_id),
            ).fetchone()
        if row is None:  # pragma: no cover - defensive database boundary.
            raise RuntimeError("Recommendation dismissal was not saved.")
        return self._row_to_item(row)

    def remove(self, media_type: MediaType, tmdb_id: int) -> bool:
        self.database.initialise()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM recommendation_dismissals
                WHERE media_type = ? AND tmdb_id = ?
                """,
                (media_type, tmdb_id),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_item(row) -> RecommendationDismissal:
        return RecommendationDismissal(
            media_type=row["media_type"],
            tmdb_id=row["tmdb_id"],
            title=row["title"],
            created_at=row["created_at"],
        )
