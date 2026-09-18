from typing import Literal

from pydantic import BaseModel, Field, model_validator


MediaType = Literal["movie", "tv"]
LibraryStatus = Literal["watchlist", "watching", "watched", "dropped"]


class MediaSearchResult(BaseModel):
    tmdb_id: int
    media_type: MediaType
    title: str
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None


class CountryAvailability(BaseModel):
    code: str
    name: str


class StreamingServiceAvailability(BaseModel):
    service_key: str
    service_name: str
    provider_ids: list[int]
    logo_path: str | None = None
    countries: list[CountryAvailability]


class MediaAvailability(BaseModel):
    tmdb_id: int
    media_type: MediaType
    title: str
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    providers: list[StreamingServiceAvailability]


class StreamingServiceOption(BaseModel):
    key: str
    name: str


class StreamingServicePreferences(BaseModel):
    services: list[str]


class MediaLibraryEntry(BaseModel):
    media_type: MediaType
    tmdb_id: int
    title: str
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    status: LibraryStatus
    favourite: bool = False
    created_at: str
    updated_at: str


class MediaLibrarySaveRequest(BaseModel):
    title: str
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    status: LibraryStatus
    favourite: bool = False


class RatingCategoryDefinition(BaseModel):
    key: str
    label: str
    maximum: float = 10.0


class RatingCategoryScore(BaseModel):
    key: str
    label: str
    score: float = Field(ge=0.0, le=10.0)


class MediaRating(BaseModel):
    media_type: MediaType
    tmdb_id: int
    title: str | None = None
    year: int | None = None
    categories: list[RatingCategoryScore]
    total: float = Field(ge=0.0, le=100.0)
    notes: str | None = None
    created_at: str
    updated_at: str


class MediaRatingSaveRequest(BaseModel):
    scores: dict[str, float]
    notes: str | None = None

    @model_validator(mode="after")
    def validate_scores(self) -> "MediaRatingSaveRequest":
        from app.services.rating_system import RATING_CATEGORY_KEYS

        expected = set(RATING_CATEGORY_KEYS)
        received = set(self.scores)
        if received != expected:
            missing = sorted(expected - received)
            extra = sorted(received - expected)
            details = []
            if missing:
                details.append(f"missing: {', '.join(missing)}")
            if extra:
                details.append(f"unknown: {', '.join(extra)}")
            raise ValueError(
                "Scores must contain every rating category ("
                + "; ".join(details)
                + ")."
            )

        for key, score in self.scores.items():
            numeric = float(score)
            if numeric < 0.0 or numeric > 10.0:
                raise ValueError(f"{key} must be between 0 and 10.")
            if round(numeric * 2) != numeric * 2:
                raise ValueError(f"{key} must use 0.5-point increments.")
        return self
