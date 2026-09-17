from typing import Literal

from pydantic import BaseModel


MediaType = Literal["movie", "tv"]


class MediaSearchResult(BaseModel):
    tmdb_id: int
    media_type: MediaType
    title: str
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None


class StreamingServiceAvailability(BaseModel):
    service_key: str
    service_name: str
    provider_ids: list[int]
    logo_path: str | None = None
    countries: list[str]


class MediaAvailability(BaseModel):
    tmdb_id: int
    media_type: MediaType
    providers: list[StreamingServiceAvailability]


class StreamingServiceOption(BaseModel):
    key: str
    name: str
