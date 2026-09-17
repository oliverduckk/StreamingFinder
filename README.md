Streaming Finder

A desktop-focused media project with a FastAPI backend for finding where movies and TV shows are available to stream across different countries.

The API is designed to be consumed by the future StreamingFinder desktop interface and by Project Mairon.

Current milestone: v0.2.1

Search movies and TV shows through TMDB.

Retrieve subscription (flatrate) streaming availability by country.

Normalise duplicate TMDB provider records into stable StreamingFinder service keys.

Filter availability to selected services such as Netflix or Amazon Prime Video.

Expose a service catalogue for the future My Streaming Services settings UI.

Setup

Create a virtual environment.

Install the project with development dependencies:
pip install -e "[dev]"

Copy .env.example to .env.

Add your TMDB API Read Access Token to .env.

Run the API:
uvicorn app.main:app --reload

Open http://127.0.0.1:8000/docs.

Current endpoints

GET /health

GET /api/v1/search?query=interstellar

GET /api/v1/services

GET /api/v1/availability/movie/157336

GET /api/v1/availability/movie/157336?services=netflix&services=prime_video

GET /api/v1/availability/movie/157336?services=netflix,prime_video

If no services filter is supplied, StreamingFinder returns all subscription providers reported by TMDB. If a filter is supplied, only the selected canonical services are returned.

Stable service keys

The application uses its own stable keys rather than storing TMDB provider IDs directly. For example, multiple TMDB records such as Amazon Prime Video and Amazon Prime Video with Ads can map to the single key prime_video.

This keeps desktop preferences and future Mairon tools independent from TMDB's internal provider IDs.

Attribution

This product uses the TMDB API but is not endorsed or certified by TMDB.

Movie and TV metadata is provided by TMDB. Streaming-provider availability uses TMDB watch-provider data powered by JustWatch. JustWatch attribution will be displayed in the finished desktop interface.