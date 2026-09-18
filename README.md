# StreamingFinder

StreamingFinder is a local desktop application and API for finding where movies and TV shows are available to stream by service and country, while building a personal media library and structured rating history.

## V0.9

V0.9 adds the first dedicated Library screen to the desktop application.

The top-level desktop navigation now contains **Search** and **Library**. The Library view reads directly from the local SQLite database and displays saved movies and TV series as poster cards with their library status, favourite state, and personal `/100` rating when available.

Library browsing supports:

- text filtering by title
- status filtering: Watchlist, Watching, Watched, Dropped
- media filtering: Movies or TV series
- favourites-only filtering
- sorting by recently updated, highest rated, title A-Z, or release year
- opening any saved title back into the full details/streaming-availability view

The library remains fully local in `data/streaming_finder.db`; personal library and rating data are not committed to Git.

## Rating system

Each movie or TV series can be scored across ten categories, each out of 10, for an overall score out of 100:

1. Story
2. Characters
3. Dialogue
4. Visuals
5. Soundtrack
6. Worldbuilding
7. Direction
8. Pacing
9. Emotional Impact
10. Enjoyment

Scores use 0.5-point increments and support optional personal notes.

## Run

```powershell
python -m pip install -e ".[dev]"
pytest
python -m app.desktop
```

TMDB metadata is used under TMDB's API terms. Streaming availability data is supplied by JustWatch via TMDB and requires appropriate attribution in the UI.
