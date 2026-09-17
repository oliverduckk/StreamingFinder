from app.models.media import CountryAvailability, MediaType

TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"


def tmdb_image_url(image_path: str | None, size: str) -> str | None:
    """Build a TMDB image URL from a path returned by the API."""
    if not image_path:
        return None
    clean_path = image_path if image_path.startswith("/") else f"/{image_path}"
    return f"{TMDB_IMAGE_BASE_URL}/{size}{clean_path}"


def poster_url(poster_path: str | None, size: str = "w342") -> str | None:
    return tmdb_image_url(poster_path, size)


def provider_logo_url(logo_path: str | None, size: str = "w92") -> str | None:
    return tmdb_image_url(logo_path, size)


def media_subtitle(media_type: MediaType, year: int | None) -> str:
    type_label = "Movie" if media_type == "movie" else "TV series"
    year_label = str(year) if year is not None else "Year unknown"
    return f"{year_label} • {type_label}"


def format_country_names(countries: list[CountryAvailability]) -> str:
    if not countries:
        return "No countries reported"
    return ", ".join(country.name for country in countries)


def split_country_preview(
    countries: list[CountryAvailability],
    limit: int = 8,
) -> tuple[list[CountryAvailability], list[CountryAvailability]]:
    """Split countries into a compact initial preview and an expandable remainder."""
    if limit < 0:
        raise ValueError("limit must be zero or greater")
    return countries[:limit], countries[limit:]
