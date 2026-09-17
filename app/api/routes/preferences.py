from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_preferences_repository
from app.models.media import StreamingServicePreferences
from app.repositories.preferences import StreamingPreferencesRepository
from app.services.streaming_services import validate_service_keys

router = APIRouter(prefix="/api/v1/preferences", tags=["preferences"])


@router.get("/services", response_model=StreamingServicePreferences)
def get_service_preferences(
    preferences: StreamingPreferencesRepository = Depends(get_preferences_repository),
) -> StreamingServicePreferences:
    return StreamingServicePreferences(
        services=preferences.get_enabled_services(),
    )


@router.put("/services", response_model=StreamingServicePreferences)
def update_service_preferences(
    payload: StreamingServicePreferences,
    preferences: StreamingPreferencesRepository = Depends(get_preferences_repository),
) -> StreamingServicePreferences:
    requested = {service.strip().casefold() for service in payload.services if service.strip()}

    try:
        validated = validate_service_keys(requested)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved = preferences.set_enabled_services(validated or set())
    return StreamingServicePreferences(services=saved)
