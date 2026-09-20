# Mairon integration contract

StreamingFinder exposes a small assistant-facing facade under `/api/v1/assistant`.
The facade keeps Mairon away from desktop UI internals and from having to coordinate
search, library, ratings, availability and recommendation endpoints itself.

## Suggested Mairon tools

### `streaming_where_to_watch`

Use for questions such as:

- "Where can I watch Interstellar?"
- "Is The Batman on any of my services?"
- "What VPN country has this on Netflix?"

HTTP mapping:

```text
GET /api/v1/assistant/where-to-watch
```

Parameters:

```text
query              required title text
media_type         optional movie | tv
year               optional release year
only_my_services   default true
```

The response contains the selected TMDB result, up to four alternatives for
ambiguity handling, the saved services considered, and country-by-country
streaming availability.

### `streaming_title_context`

Use when Mairon needs to know what the user has already recorded about a title:

- watched/watchlist state
- favourite state
- structured category rating
- total /100 score
- notes

HTTP mapping:

```text
GET /api/v1/assistant/title-context
```

Set `include_availability=true` only when streaming availability is also needed.
This avoids unnecessary TMDB requests for ordinary library/rating questions.

### `streaming_recommendations`

Use for questions such as:

- "What should I watch tonight?"
- "Recommend an anime series."
- "Give me five familiar movie picks on my services."

HTTP mapping:

```text
GET /api/v1/assistant/recommendations
```

Parameters:

```text
media_type       all | movie | tv | anime | anime_movie | anime_tv
limit            1-12, default 5
discovery_mode   familiar | balanced | hidden
only_my_services default true
```

The response deliberately exposes StreamingFinder's deterministic match score and
reason list. Mairon should describe it as a ranking score, not as a probability
that the user will enjoy the title.

### `streaming_profile`

Use when Mairon needs broader taste context for recommendations or banter.

HTTP mapping:

```text
GET /api/v1/assistant/profile
```

The response includes library counts, ratings dashboard data, category taste
signals, cached metadata affinities, and recommendation-feedback totals.

## Local development

Run the API separately with:

```powershell
uvicorn app.main:app --reload
```

The desktop app can continue to run with:

```powershell
python -m app.desktop
```

A later Mairon-side integration can call the assistant endpoints over localhost
without depending on any Qt code.

## Runtime note

From V0.16 onward, launching the installed StreamingFinder desktop application also starts the local API on `http://127.0.0.1:8000`. Mairon can therefore use these endpoints whenever StreamingFinder is running without requiring a separate Uvicorn terminal. Source/development workflows may still start Uvicorn manually if preferred.
