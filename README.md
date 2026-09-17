# Streaming Finder

A desktop-focused media project with a FastAPI backend for finding where movies and TV shows are available to stream across different countries.

The API is designed to be consumed by the future StreamingFinder desktop interface and by Project Mairon.

## Current milestone: v0.3.0

- Search movies and TV shows through TMDB.
- Retrieve subscription (`flatrate`) streaming availability by country.
- Normalise duplicate TMDB provider records into stable StreamingFinder service keys.
- Filter availability to selected services such as Netflix or Amazon Prime Video.
- Persist **My Streaming Services** locally in SQLite.
- Let availability searches automatically use the saved subscription list.

## Setup

1. Create and activate a virtual environment.
2. Install the project with development dependencies:
   `pip install -e ".[dev]"`
3. Copy `.env.example` to `.env`.
4. Add your TMDB API Read Access Token to `.env`.
5. Run the API:
   `uvicorn app.main:app --reload`
6. Open `http://127.0.0.1:8000/docs`.

SQLite is part of Python, so v0.3 does not add another database dependency. The local database is created automatically at `data/streaming_finder.db` and is ignored by Git.

## Current endpoints

- `GET /health`
- `GET /api/v1/search?query=interstellar`
- `GET /api/v1/services`
- `GET /api/v1/preferences/services`
- `PUT /api/v1/preferences/services`
- `GET /api/v1/availability/movie/157336`
- `GET /api/v1/availability/movie/157336?services=netflix,prime_video`
- `GET /api/v1/availability/movie/157336?my_services=true`

### Save My Streaming Services

Send JSON to `PUT /api/v1/preferences/services`:

```json
{
  "services": [
    "netflix",
    "prime_video",
    "disney_plus"
  ]
}
```

Then use `my_services=true` on an availability request to filter using the saved subscription list.

Explicit `services=...` and `my_services=true` cannot be used together.

## Stable service keys

The application uses its own stable keys rather than storing TMDB provider IDs directly. For example, multiple TMDB records such as `Amazon Prime Video` and `Amazon Prime Video with Ads` can map to the single key `prime_video`.

This keeps desktop preferences, the local database and future Mairon tools independent from TMDB's internal provider IDs.

## Local data

Personal data such as selected subscriptions is stored locally and is not committed to the public repository. The same local database can later grow to hold watch history, ratings, favourites and recommendation data.

## Attribution

This product uses the TMDB API but is not endorsed or certified by TMDB.

Movie and TV metadata is provided by TMDB. Streaming-provider availability uses TMDB watch-provider data powered by JustWatch. JustWatch attribution will be displayed in the finished desktop interface.
