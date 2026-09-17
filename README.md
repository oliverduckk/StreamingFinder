# StreamingFinder

StreamingFinder is a local-first movie and TV streaming availability project. It uses TMDB metadata and watch-provider data to search titles, normalise streaming services, save local subscription preferences, and show which countries carry a title on selected services.

> This product uses the TMDB API but is not endorsed or certified by TMDB.
>
> Streaming availability data is provided through TMDB's partnership with JustWatch. JustWatch attribution is required when this data is displayed in the final application.

## Current capabilities

- Search movies and TV shows through TMDB.
- Retrieve subscription (`flatrate`) streaming availability by country.
- Canonicalise duplicate provider variants into stable services such as Netflix and Amazon Prime Video.
- Save "My Streaming Services" locally in SQLite.
- Filter availability using saved streaming subscriptions.
- Return human-readable country names while preserving ISO country codes.
- Return title, year, overview, and poster metadata with availability results.

## Development setup

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and add your TMDB API Read Access Token:

```env
TMDB_READ_ACCESS_TOKEN=replace_me
```

Run the API:

```powershell
uvicorn app.main:app --reload
```

Run tests:

```powershell
pytest
```

## Useful endpoints

Search:

```text
GET /api/v1/search?query=Interstellar
```

Available canonical services:

```text
GET /api/v1/services
```

Saved services:

```text
GET /api/v1/preferences/services
PUT /api/v1/preferences/services
```

Availability using saved services:

```text
GET /api/v1/availability/movie/157336?my_services=true
```

Availability responses include title metadata and country objects such as:

```json
{
  "code": "AU",
  "name": "Australia"
}
```

## Direction

StreamingFinder is intended to become a desktop application with a personal media library, rating system, watch history, recommendations, and integration with Project Mairon.
