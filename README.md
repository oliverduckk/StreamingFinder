# StreamingFinder

StreamingFinder is a local desktop media app and API for finding where movies and TV shows stream around the world, tracking a personal media library, rating titles with a structured /100 system, and building transparent taste-based recommendations.

## V0.16 — Windows desktop application

V0.16 can be installed as a normal clickable Windows application. The installed build:

- creates `StreamingFinder.exe` with no console window,
- creates Desktop and Start Menu shortcuts,
- migrates the existing `.env` and SQLite library into `%LOCALAPPDATA%\StreamingFinder`,
- keeps personal data outside the executable so future app updates do not overwrite it, and
- starts the local FastAPI service silently on `127.0.0.1:8000` while the desktop app is running.

From an activated virtual environment, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\install_windows.ps1
```

After installation, StreamingFinder can be launched directly from the desktop or Start Menu. VS Code and the Python virtual environment are not required to run the installed application.

The installed files live under `%LOCALAPPDATA%\Programs\StreamingFinder`, while the TMDB configuration and SQLite database live under `%LOCALAPPDATA%\StreamingFinder`.

To remove the application while preserving personal data:

```powershell
.\scripts\uninstall_windows.ps1
```

To also remove the local library, ratings and configuration:

```powershell
.\scripts\uninstall_windows.ps1 -RemoveData
```

## V0.15 — Assistant integration API

V0.15 adds a tool-oriented API facade designed for future Mairon integration. The desktop app remains independent, while Mairon can consume structured StreamingFinder data without knowing how the GUI, SQLite repositories or TMDB orchestration work internally.

### Assistant endpoints

```text
GET /api/v1/assistant/where-to-watch
GET /api/v1/assistant/title-context
GET /api/v1/assistant/recommendations
GET /api/v1/assistant/profile
```

Examples:

```text
/api/v1/assistant/where-to-watch?query=Interstellar
/api/v1/assistant/title-context?query=Interstellar&media_type=movie&year=2014
/api/v1/assistant/recommendations?media_type=movie&limit=5&discovery_mode=familiar
/api/v1/assistant/profile
```

Title resolution prefers exact title matches and can use optional media type/year hints. Responses also include alternative TMDB matches so an assistant can ask for clarification rather than silently selecting an ambiguous title.

The profile endpoint combines local library counts, ratings dashboard data, category-level taste signals, cached metadata affinities and recommendation-feedback totals into one assistant-friendly response.

See [`docs/MAIRON_INTEGRATION.md`](docs/MAIRON_INTEGRATION.md) for the suggested Mairon tool contract.

## Run desktop app

```powershell
python -m pip install -e ".[dev]"
pytest
python -m app.desktop
```

## Run API

```powershell
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000/docs
```

## Existing API highlights

```text
GET /api/v1/search?query=Interstellar
GET /api/v1/availability/movie/157336?my_services=true
GET /api/v1/library
GET /api/v1/ratings/dashboard
GET /api/v1/ratings/taste-profile
GET /api/v1/ratings/metadata-profile
GET /api/v1/recommendations
GET /api/v1/recommendation-feedback/summary
```

Streaming availability data is supplied through TMDB's JustWatch integration. The desktop UI includes the required attribution.
