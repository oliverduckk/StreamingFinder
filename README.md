# StreamingFinder

StreamingFinder is a local desktop media app and API for finding where movies and TV shows stream around the world, tracking a personal media library, rating titles with a structured /100 system, and building transparent taste-based recommendations.

## V0.13.4 — Broader anime-series discovery

V0.13.4 fixes the remaining anime-series starvation bug. Anime recommendations were still being discovered through an overly narrow combination of the user's strongest genres, which could leave only one or two unseen series even when the library contained dozens of rated anime.

### New in this milestone

- Anime-series discovery now always includes a broad **Japanese + Animation** TMDB query, independent of taste genres.
- The broader catalogue is searched across the mature-library pagination depth introduced in V0.13.3.
- Additional single-genre taste searches are still performed so the user's metadata profile influences which candidates enter the pool.
- The local taste model continues to rank the combined pool; broader discovery does not mean random recommendations.
- `TMDBClient.discover_media()` now supports a required genre without also requiring taste-genre IDs, allowing a true broad anime catalogue query.
- New regression coverage verifies both the broad-service discovery path and the actual TMDB query parameters.
- Crunchyroll/provider availability is **not** used to generate candidates unless **Only my services** is enabled; provider filtering remains a later availability step.

## Run

```powershell
python -m pip install -e ".[dev]"
pytest
python -m app.desktop
```

## API highlights

```text
GET /api/v1/search?query=Interstellar
GET /api/v1/availability/movie/157336?my_services=true
GET /api/v1/library
GET /api/v1/ratings/dashboard
GET /api/v1/ratings/taste-profile
GET /api/v1/ratings/metadata-profile
GET /api/v1/recommendations
```

Streaming availability data is supplied through TMDB's JustWatch integration. The desktop UI includes the required attribution.
