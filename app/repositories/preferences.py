from app.db.database import SQLiteDatabase
from app.services.streaming_services import order_service_keys


class StreamingPreferencesRepository:
    """Persist the user's currently enabled streaming subscriptions."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get_enabled_services(self) -> list[str]:
        self.database.initialise()

        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT service_key
                FROM streaming_service_preferences
                WHERE enabled = 1
                """
            ).fetchall()

        return order_service_keys({row["service_key"] for row in rows})

    def set_enabled_services(self, service_keys: set[str]) -> list[str]:
        self.database.initialise()

        with self.database.connect() as connection:
            connection.execute("DELETE FROM streaming_service_preferences")
            connection.executemany(
                """
                INSERT INTO streaming_service_preferences (service_key, enabled)
                VALUES (?, 1)
                """,
                [(service_key,) for service_key in order_service_keys(service_keys)],
            )

        return self.get_enabled_services()
