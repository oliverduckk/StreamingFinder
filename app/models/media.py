from typing import Literal

from pydantic import BaseModel


class MediaSearchResult(BaseModel):
    tmdb_id: int
    media_type: Literal["movie", "tv"]
    title: str
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None
