from app.db.database import SQLiteDatabase
from app.models.media import MediaRating, MediaType, RatingCategoryScore
from app.services.rating_system import RATING_CATEGORIES, RATING_CATEGORY_KEYS, rating_total


class MediaRatingRepository:
    """Persist structured personal ratings for movies and TV series."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get(self, media_type: MediaType, tmdb_id: int) -> MediaRating | None:
        self.database.initialise()
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT r.media_type, r.tmdb_id, r.notes, r.created_at, r.updated_at,
                       l.title, l.year
                FROM media_ratings AS r
                LEFT JOIN media_library AS l
                  ON l.media_type = r.media_type AND l.tmdb_id = r.tmdb_id
                WHERE r.media_type = ? AND r.tmdb_id = ?
                """,
                (media_type, tmdb_id),
            ).fetchone()
            if row is None:
                return None

            score_rows = connection.execute(
                """
                SELECT category_key, score
                FROM media_rating_scores
                WHERE media_type = ? AND tmdb_id = ?
                """,
                (media_type, tmdb_id),
            ).fetchall()

        return self._build_rating(row, score_rows)

    def list(self, *, media_type: MediaType | None = None) -> list[MediaRating]:
        self.database.initialise()
        where = "WHERE r.media_type = ?" if media_type is not None else ""
        values: tuple[object, ...] = (media_type,) if media_type is not None else ()
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT r.media_type, r.tmdb_id, r.notes, r.created_at, r.updated_at,
                       l.title, l.year
                FROM media_ratings AS r
                LEFT JOIN media_library AS l
                  ON l.media_type = r.media_type AND l.tmdb_id = r.tmdb_id
                {where}
                ORDER BY r.updated_at DESC, l.title COLLATE NOCASE ASC
                """,
                values,
            ).fetchall()

            ratings: list[MediaRating] = []
            for row in rows:
                score_rows = connection.execute(
                    """
                    SELECT category_key, score
                    FROM media_rating_scores
                    WHERE media_type = ? AND tmdb_id = ?
                    """,
                    (row["media_type"], row["tmdb_id"]),
                ).fetchall()
                ratings.append(self._build_rating(row, score_rows))

        return ratings

    def upsert(
        self,
        media_type: MediaType,
        tmdb_id: int,
        scores: dict[str, float],
        *,
        notes: str | None = None,
    ) -> MediaRating:
        self.database.initialise()
        missing = [key for key in RATING_CATEGORY_KEYS if key not in scores]
        extra = [key for key in scores if key not in RATING_CATEGORY_KEYS]
        if missing or extra:
            raise ValueError("Scores must contain exactly the configured rating categories.")

        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO media_ratings (media_type, tmdb_id, notes, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(media_type, tmdb_id) DO UPDATE SET
                    notes = excluded.notes,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (media_type, tmdb_id, notes),
            )
            for category in RATING_CATEGORIES:
                connection.execute(
                    """
                    INSERT INTO media_rating_scores (
                        media_type, tmdb_id, category_key, score
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(media_type, tmdb_id, category_key) DO UPDATE SET
                        score = excluded.score
                    """,
                    (media_type, tmdb_id, category.key, float(scores[category.key])),
                )

        rating = self.get(media_type, tmdb_id)
        if rating is None:  # pragma: no cover - defensive database boundary.
            raise RuntimeError("Media rating was not saved.")
        return rating

    def remove(self, media_type: MediaType, tmdb_id: int) -> bool:
        self.database.initialise()
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM media_ratings WHERE media_type = ? AND tmdb_id = ?",
                (media_type, tmdb_id),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _build_rating(row, score_rows) -> MediaRating:
        score_map = {
            score_row["category_key"]: float(score_row["score"])
            for score_row in score_rows
        }
        categories = [
            RatingCategoryScore(
                key=category.key,
                label=category.label,
                score=score_map.get(category.key, 0.0),
            )
            for category in RATING_CATEGORIES
        ]
        return MediaRating(
            media_type=row["media_type"],
            tmdb_id=row["tmdb_id"],
            title=row["title"],
            year=row["year"],
            categories=categories,
            total=rating_total(score_map),
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
