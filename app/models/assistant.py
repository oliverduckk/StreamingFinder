from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.media import (
    MediaAvailability,
    MediaLibraryEntry,
    MediaRating,
    MediaSearchResult,
    MetadataTasteProfile,
    RatingsDashboard,
    RecommendationFeedbackSummary,
    TasteProfile,
)


class AssistantTitleResolution(BaseModel):
    query: str
    selected: MediaSearchResult
    alternatives: list[MediaSearchResult] = Field(default_factory=list)
    exact_title_match: bool = False
    year_match: bool | None = None


class AssistantWhereToWatchResponse(BaseModel):
    resolution: AssistantTitleResolution
    only_my_services: bool
    services_considered: list[str] = Field(default_factory=list)
    availability: MediaAvailability


class AssistantTitleContextResponse(BaseModel):
    resolution: AssistantTitleResolution
    library_entry: MediaLibraryEntry | None = None
    rating: MediaRating | None = None
    watched: bool = False
    on_watchlist: bool = False
    availability: MediaAvailability | None = None


class AssistantLibrarySummary(BaseModel):
    total: int = Field(ge=0)
    watchlist: int = Field(ge=0)
    watching: int = Field(ge=0)
    watched: int = Field(ge=0)
    dropped: int = Field(ge=0)
    favourites: int = Field(ge=0)


class AssistantProfileResponse(BaseModel):
    library: AssistantLibrarySummary
    ratings: RatingsDashboard
    taste: TasteProfile
    metadata: MetadataTasteProfile
    recommendation_feedback: RecommendationFeedbackSummary
