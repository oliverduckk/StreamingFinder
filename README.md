# StreamingFinder

StreamingFinder is a local-first desktop app and API for finding where movies and TV shows are available to stream around the world. It uses TMDB metadata and watch-provider data, normalises provider variants, saves local subscription preferences, and filters availability to the services you actually use.

> This product uses the TMDB API but is not endorsed or certified by TMDB.
>
> Streaming availability data is provided through TMDB's partnership with JustWatch. JustWatch attribution is required when this data is displayed.

## Current capabilities

- Native PySide6 desktop interface with a dark purple-accented theme.
- Search movies and TV shows through TMDB.
- Display posters, title metadata, overview text, and search results.
- Retrieve subscription (`flatrate`) streaming availability by country.
- Canonicalise duplicate provider variants into stable services such as Netflix and Amazon Prime Video.
- Save "My Streaming Services" locally in SQLite.
- Automatically refresh availability when selected subscriptions change.
- Display streaming provider logos.
- Display countries as compact expandable chips instead of long text blocks.
- Show a non-blocking loading indicator while network requests run.
- Return human-readable country names while preserving ISO country codes.
- Expose the same backend through FastAPI for future Mairon integration.

## Development setup

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and add your TMDB API Read Access Token:

```env
TMDB_READ_ACCESS_TOKEN=replace_me
```

Launch the desktop app:

```powershell
python -m app.desktop
```

or:

```powershell
streaming-finder
```

Run tests:

```powershell
pytest
```

Run the API independently when needed:

```powershell
uvicorn app.main:app --reload
```

## Direction

The next major area is the personal media library: watched status, watchlist, favourites, a detailed rating system, viewing history, recommendation data, and integration with Project Mairon.
