# StreamingFinder

StreamingFinder is a local-first desktop application and API for finding where movies and TV shows are available to stream across countries. It uses TMDB metadata and watch-provider data, normalises streaming services, stores local subscription preferences, and is being designed for later integration with Project Mairon.

> This product uses the TMDB API but is not endorsed or certified by TMDB.
>
> Streaming availability data is provided through TMDB's partnership with JustWatch. JustWatch attribution is required when this data is displayed in the application.

## Current capabilities

- Native PySide6 desktop application.
- Dark media-focused interface designed to sit alongside Project Mairon.
- Search movies and TV shows through TMDB.
- Display posters, title metadata, overview, and streaming availability.
- Retrieve subscription (`flatrate`) streaming availability by country.
- Canonicalise duplicate provider variants into stable services such as Netflix and Amazon Prime Video.
- Save "My Streaming Services" locally in SQLite.
- Change streaming subscriptions from desktop checkboxes and persist them automatically.
- Filter availability using selected subscriptions.
- Return human-readable country names while preserving ISO country codes.
- FastAPI interface remains available for future Mairon and Raspberry Pi clients.

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

## Run the desktop app

The desktop app talks directly to the shared StreamingFinder backend code, so Uvicorn does not need to be running for normal desktop use.

```powershell
python -m app.desktop
```

After installation you can also run:

```powershell
streaming-finder
```

## Run the API

The API remains available as a separate interface for future Mairon/Pi integration:

```powershell
uvicorn app.main:app --reload
```

## Run tests

```powershell
pytest
```

## Useful API endpoints

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

## Direction

The next major areas are the personal media library, custom rating system, watch history/watchlist, personalised recommendations, and Project Mairon integration.
