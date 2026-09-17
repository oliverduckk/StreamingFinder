from app.gui.helpers import format_country_names, media_subtitle, poster_url
from app.models.media import CountryAvailability


def test_media_subtitle_formats_movie_and_tv() -> None:
    assert media_subtitle("movie", 2014) == "2014 • Movie"
    assert media_subtitle("tv", 2022) == "2022 • TV series"


def test_poster_url_and_country_formatting() -> None:
    assert poster_url("/poster.jpg", "w185") == (
        "https://image.tmdb.org/t/p/w185/poster.jpg"
    )
    assert poster_url(None) is None

    countries = [
        CountryAvailability(code="AU", name="Australia"),
        CountryAvailability(code="JP", name="Japan"),
    ]
    assert format_country_names(countries) == "Australia, Japan"
