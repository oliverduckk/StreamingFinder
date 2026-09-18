from pathlib import Path
import sqlite3


class SQLiteDatabase:
    """Small SQLite wrapper used by StreamingFinder's local data layer."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialise(self) -> None:
        """Create the current schema when it does not already exist."""
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS streaming_service_preferences (
                    service_key TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS media_library (
                    media_type TEXT NOT NULL CHECK (media_type IN ('movie', 'tv')),
                    tmdb_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    year INTEGER,
                    overview TEXT,
                    poster_path TEXT,
                    status TEXT NOT NULL CHECK (
                        status IN ('watchlist', 'watching', 'watched', 'dropped')
                    ),
                    favourite INTEGER NOT NULL DEFAULT 0 CHECK (favourite IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (media_type, tmdb_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS media_ratings (
                    media_type TEXT NOT NULL CHECK (media_type IN ('movie', 'tv')),
                    tmdb_id INTEGER NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (media_type, tmdb_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS media_rating_scores (
                    media_type TEXT NOT NULL,
                    tmdb_id INTEGER NOT NULL,
                    category_key TEXT NOT NULL,
                    score REAL NOT NULL CHECK (score >= 0 AND score <= 10),
                    PRIMARY KEY (media_type, tmdb_id, category_key),
                    FOREIGN KEY (media_type, tmdb_id)
                        REFERENCES media_ratings(media_type, tmdb_id)
                        ON DELETE CASCADE
                )
                """
            )
