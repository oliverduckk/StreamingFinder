# Streaming Finder

A FastAPI application for finding where movies and TV shows are available to stream across different countries.

## V0.1 goal

Search for a movie or TV show by title and return normalized TMDB search results. Streaming availability will be added in the next milestone.

## Setup

1. Create a virtual environment.
2. Install the project with development dependencies:
   `pip install -e ".[dev]"`
3. Copy `.env.example` to `.env`.
4. Add your TMDB API Read Access Token to `.env`.
5. Run the API:
   `uvicorn app.main:app --reload`
6. Open `http://127.0.0.1:8000/docs`.

## Current endpoints

- `GET /health`
- `GET /api/v1/search?query=interstellar`

## Attribution

This product uses the TMDB API but is not endorsed or certified by TMDB.

Movie and TV metadata is provided by TMDB. Streaming-provider availability added in future versions will use TMDB watch-provider data powered by JustWatch and will include the required JustWatch attribution.
