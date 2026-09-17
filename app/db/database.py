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
