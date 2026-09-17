# StreamingFinder

StreamingFinder is a local desktop application and API for finding where movies and TV shows are available to stream by service and country.

## V0.7

V0.7 adds the first personal media-library foundation:

- persistent SQLite movie/TV library
- Watchlist, Watching, Watched and Dropped statuses
- Favourite toggle
- automatic persistence from the desktop title panel
- REST endpoints under `/api/v1/library` for future Mairon integration
- library metadata stores TMDB ID, media type, title, year, overview and poster path

The database remains local in `data/streaming_finder.db` and is not committed to Git.

## Run

```powershell
python -m pip install -e ".[dev]"
pytest
python -m app.desktop
```

TMDB metadata is used under TMDB's API terms. Streaming availability data is supplied by JustWatch via TMDB and requires appropriate attribution in the UI.
