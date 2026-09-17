from app.models.media import CountryAvailability, MediaType

TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"


def poster_url(poster_path: str | None, size: str = "w342") -> str | None:
    """Build a TMDB poster URL for a poster path returned by the API."""
    if not poster_path:
        return None
    clean_path = poster_path if poster_path.startswith("/") else f"/{poster_path}"
    return f"{TMDB_IMAGE_BASE_URL}/{size}{clean_path}"


def media_subtitle(media_type: MediaType, year: int | None) -> str:
    type_label = "Movie" if media_type == "movie" else "TV series"
    year_label = str(year) if year is not None else "Year unknown"
    return f"{year_label} • {type_label}"


def format_country_names(countries: list[CountryAvailability]) -> str:
    if not countries:
        return "No countries reported"
    return ", ".join(country.name for country in countries)
