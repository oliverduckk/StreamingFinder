from pathlib import Path

from app.db.database import SQLiteDatabase
from app.repositories.dismissals import RecommendationDismissalRepository


def test_recommendation_dismissals_persist_and_can_be_removed(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "dismissals.db")
    repository = RecommendationDismissalRepository(database)

    saved = repository.add("movie", 123, "No Thanks")

    assert saved.title == "No Thanks"
    assert repository.contains("movie", 123) is True
    assert {(item.media_type, item.tmdb_id) for item in repository.list()} == {
        ("movie", 123)
    }

    assert repository.remove("movie", 123) is True
    assert repository.contains("movie", 123) is False
