from __future__ import annotations

from app.db.database import SQLiteDatabase
from app.models.media import (
    MediaType,
    RecommendationFeedbackAction,
    RecommendationFeedbackEntry,
    RecommendationFeedbackSummary,
)


class RecommendationFeedbackRepository:
    """Persist lightweight reactions to recommendation cards.

    Reactions are aggregated per title instead of storing an unbounded click log.
    This keeps the local database small while preserving enough information for
    the recommendation engine to learn from repeated behaviour.
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def list(self) -> list[RecommendationFeedbackEntry]:
        self.database.initialise()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT media_type, tmdb_id, title,
                       open_count, watchlist_count, watched_count,
                       not_interested_count, last_action, created_at, updated_at
                FROM recommendation_feedback
                ORDER BY updated_at DESC, title COLLATE NOCASE ASC
                """
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def get(self, media_type: MediaType, tmdb_id: int) -> RecommendationFeedbackEntry | None:
        self.database.initialise()
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT media_type, tmdb_id, title,
                       open_count, watchlist_count, watched_count,
                       not_interested_count, last_action, created_at, updated_at
                FROM recommendation_feedback
                WHERE media_type = ? AND tmdb_id = ?
                """,
                (media_type, tmdb_id),
            ).fetchone()
        return self._row_to_item(row) if row is not None else None

    def record(
        self,
        media_type: MediaType,
        tmdb_id: int,
        title: str,
        action: RecommendationFeedbackAction,
    ) -> RecommendationFeedbackEntry:
        self.database.initialise()
        increments = {
            "open_details": (1, 0, 0, 0),
            "watchlist": (0, 1, 0, 0),
            "watched": (0, 0, 1, 0),
            "not_interested": (0, 0, 0, 1),
        }
        open_inc, watchlist_inc, watched_inc, not_interested_inc = increments[action]
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO recommendation_feedback (
                    media_type, tmdb_id, title,
                    open_count, watchlist_count, watched_count, not_interested_count,
                    last_action
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(media_type, tmdb_id) DO UPDATE SET
                    title = excluded.title,
                    open_count = recommendation_feedback.open_count + excluded.open_count,
                    watchlist_count = recommendation_feedback.watchlist_count + excluded.watchlist_count,
                    watched_count = recommendation_feedback.watched_count + excluded.watched_count,
                    not_interested_count = recommendation_feedback.not_interested_count + excluded.not_interested_count,
                    last_action = excluded.last_action,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    media_type,
                    tmdb_id,
                    title,
                    open_inc,
                    watchlist_inc,
                    watched_inc,
                    not_interested_inc,
                    action,
                ),
            )
        item = self.get(media_type, tmdb_id)
        if item is None:  # pragma: no cover - defensive database boundary.
            raise RuntimeError("Recommendation feedback was not saved.")
        return item

    def remove(self, media_type: MediaType, tmdb_id: int) -> bool:
        self.database.initialise()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM recommendation_feedback
                WHERE media_type = ? AND tmdb_id = ?
                """,
                (media_type, tmdb_id),
            )
        return cursor.rowcount > 0

    def summary(self) -> RecommendationFeedbackSummary:
        items = self.list()
        from app.services.recommendation_feedback import feedback_signal

        return RecommendationFeedbackSummary(
            titles_observed=len(items),
            opened=sum(item.open_count for item in items),
            watchlisted=sum(item.watchlist_count for item in items),
            watched=sum(item.watched_count for item in items),
            not_interested=sum(item.not_interested_count for item in items),
            positive_signal_titles=sum(1 for item in items if feedback_signal(item) > 0.05),
            negative_signal_titles=sum(1 for item in items if feedback_signal(item) < -0.05),
        )

    @staticmethod
    def _row_to_item(row) -> RecommendationFeedbackEntry:
        return RecommendationFeedbackEntry(
            media_type=row["media_type"],
            tmdb_id=row["tmdb_id"],
            title=row["title"],
            open_count=row["open_count"],
            watchlist_count=row["watchlist_count"],
            watched_count=row["watched_count"],
            not_interested_count=row["not_interested_count"],
            last_action=row["last_action"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
