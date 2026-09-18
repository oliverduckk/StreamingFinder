# StreamingFinder V0.12.3 — Anime Library Filter + Recommendation Discovery Modes

V0.12.3 focuses on two issues found during real use: the Library needed the same anime/live-action split as Recommendations, and live-action TV recommendations were still surfacing too many obscure titles by default.

## Library changes

The Library content filter is now:

```text
Everything
Movies
TV series (live action)
Anime
```

Anime includes both anime films and anime series. Movies and TV series exclude titles classified as anime.

New TMDB search results are classified immediately using original language + Animation genre metadata. Existing library rows are lazily classified the first time the Library is opened after upgrading, then the result is persisted in SQLite so this is a one-time backfill rather than a repeated network cost.

## Recommendation discovery styles

Recommendations now include a second selector:

```text
Familiar
Balanced
Hidden gems
```

**Familiar** is the desktop default. It favours titles with stronger TMDB audience/popularity evidence and uses popularity-sorted discovery, so live-action TV should lean toward recognisable candidates rather than tiny-vote curiosities.

**Balanced** keeps a wider candidate pool while still applying quality floors.

**Hidden gems** deliberately permits much smaller TMDB audiences when you want obscure recommendations.

The recommendation scorer also now:

- reduces the influence of extremely generic genres that appear across most of the user's rated titles;
- scales TMDB seed/consensus bonuses by actual metadata alignment, so a weird TMDB "similar" link cannot dominate on its own;
- uses stricter vote-confidence thresholds in Familiar mode;
- adds a familiarity signal from TMDB vote count/popularity;
- preserves positive/negative taste modelling, franchise diversity, anime/live-action separation, watch-history exclusion and streaming-service filtering.

The displayed Match score is still a deterministic local ranking score, not a probability of enjoyment.

## API

```text
GET /api/v1/recommendations?media_type=tv&discovery_mode=familiar
GET /api/v1/recommendations?media_type=anime&discovery_mode=balanced
GET /api/v1/recommendations?media_type=movie&discovery_mode=hidden
```

`discovery_mode` accepts `familiar`, `balanced`, or `hidden`.

## Run

```powershell
python -m pip install -e ".[dev]"
pytest
python -m app.desktop
```

Expected test result for this patch: **61 passed**.

## Attribution

This product uses the TMDB API but is not endorsed or certified by TMDB.  
Streaming availability data is provided by JustWatch via TMDB and requires JustWatch attribution when displayed.
