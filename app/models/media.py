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
    genre_ids: list[int] = Field(default_factory=list)
    original_language: str | None = None
    is_anime: bool | None = None


class RecommendationCandidate(MediaSearchResult):
    vote_average: float = 0.0
    vote_count: int = 0
    popularity: float = 0.0


class MediaFeatureProfile(BaseModel):
    media_type: MediaType
    tmdb_id: int
    genre_ids: list[int] = Field(default_factory=list)
    genre_names: list[str] = Field(default_factory=list)
    keyword_ids: list[int] = Field(default_factory=list)
    keyword_names: list[str] = Field(default_factory=list)
    collection_id: int | None = None
    collection_name: str | None = None
    creators: list[str] = Field(default_factory=list)
    original_language: str | None = None
    is_anime: bool = False


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
    is_anime: bool | None = None
    status: LibraryStatus
    favourite: bool = False
    created_at: str
    updated_at: str


class MediaLibrarySaveRequest(BaseModel):
    title: str
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    is_anime: bool | None = None
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


class RatingCategoryAverage(BaseModel):
    key: str
    label: str
    average: float | None = None


class RatedTitleSummary(BaseModel):
    media_type: MediaType
    tmdb_id: int
    title: str
    year: int | None = None
    poster_path: str | None = None
    total: float = Field(ge=0.0, le=100.0)
    favourite: bool = False
    updated_at: str


class RatingsDashboard(BaseModel):
    total_rated: int
    average_total: float | None = None
    highest_total: float | None = None
    movie_average: float | None = None
    tv_average: float | None = None
    category_averages: list[RatingCategoryAverage]
    top_rated: list[RatedTitleSummary]
    recent_rated: list[RatedTitleSummary]


class TasteCategorySignal(BaseModel):
    key: str
    label: str
    average: float
    delta_from_personal_mean: float


class TasteAlignmentSignal(BaseModel):
    key: str
    label: str
    correlation: float
    sample_size: int


class TasteProfile(BaseModel):
    total_rated: int
    confidence: Literal["empty", "early", "developing", "established"]
    average_total: float | None = None
    score_spread: float | None = None
    strongest_categories: list[TasteCategorySignal]
    enjoyment_alignments: list[TasteAlignmentSignal]
    favourite_average: float | None = None
    non_favourite_average: float | None = None
    favourite_delta: float | None = None
    summary: str


class RecommendationDismissal(BaseModel):
    media_type: MediaType
    tmdb_id: int
    title: str
    created_at: str


class RecommendationItem(BaseModel):
    media_type: MediaType
    tmdb_id: int
    title: str
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    is_anime: bool = False
    match_score: float = Field(ge=0.0, le=100.0)
    tmdb_vote_average: float = Field(ge=0.0, le=10.0)
    tmdb_vote_count: int = Field(ge=0)
    seed_titles: list[str]
    reasons: list[str]
    on_watchlist: bool = False
    genre_names: list[str] = Field(default_factory=list)
    collection_id: int | None = None
    collection_name: str | None = None
    providers: list[StreamingServiceAvailability]


class RecommendationResponse(BaseModel):
    media_filter: Literal["all", "movie", "tv", "anime", "anime_movie", "anime_tv"]
    discovery_mode: Literal["familiar", "balanced", "hidden"] = "balanced"
    only_my_services: bool
    generated_from: int = Field(ge=0)
    total_considered: int = Field(ge=0)
    message: str
    items: list[RecommendationItem]



class MetadataAffinitySignal(BaseModel):
    kind: Literal["genre", "keyword", "creator"]
    key: str
    label: str
    affinity: float = Field(ge=-1.0, le=1.0)
    sample_size: int = Field(ge=1)
    positive_evidence: int = Field(ge=0)
    negative_evidence: int = Field(ge=0)
    supporting_titles: list[str] = Field(default_factory=list)


class MetadataTasteProfile(BaseModel):
    total_rated: int = Field(ge=0)
    metadata_coverage: int = Field(ge=0)
    confidence: Literal["empty", "early", "developing", "established"]
    positive_genres: list[MetadataAffinitySignal] = Field(default_factory=list)
    negative_genres: list[MetadataAffinitySignal] = Field(default_factory=list)
    positive_keywords: list[MetadataAffinitySignal] = Field(default_factory=list)
    negative_keywords: list[MetadataAffinitySignal] = Field(default_factory=list)
    positive_creators: list[MetadataAffinitySignal] = Field(default_factory=list)
    negative_creators: list[MetadataAffinitySignal] = Field(default_factory=list)
    summary: str
