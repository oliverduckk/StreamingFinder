from fastapi import FastAPI

from app.api.routes.availability import router as availability_router
from app.api.routes.health import router as health_router
from app.api.routes.library import router as library_router
from app.api.routes.preferences import router as preferences_router
from app.api.routes.ratings import router as ratings_router
from app.api.routes.search import router as search_router
from app.api.routes.services import router as services_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.include_router(health_router)
app.include_router(search_router)
app.include_router(availability_router)
app.include_router(services_router)
app.include_router(preferences_router)
app.include_router(library_router)
app.include_router(ratings_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }
