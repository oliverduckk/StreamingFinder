import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.api.dependencies import get_tmdb_client
from app.clients.tmdb import TMDBClient
from app.models.media import MediaAvailability, MediaType
from app.services.streaming_services import (
    parse_requested_service_keys,
    validate_service_keys,
)

router = APIRouter(prefix="/api/v1", tags=["availability"])


@router.get(
    "/availability/{media_type}/{tmdb_id}",
    response_model=MediaAvailability,
)
async def get_availability(
    media_type: MediaType,
    tmdb_id: int = Path(gt=0),
    services: list[str] | None = Query(
        default=None,
        description=(
            "Optional stable service keys. Repeat the parameter or pass a "
            "comma-separated list, e.g. netflix,prime_video."
        ),
    ),
    tmdb: TMDBClient = Depends(get_tmdb_client),
) -> MediaAvailability:
    try:
        service_keys = validate_service_keys(parse_requested_service_keys(services))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return await tmdb.get_subscription_availability(
            media_type,
            tmdb_id,
            service_keys=service_keys,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Media item was not found on TMDB.",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail="TMDB returned an error while retrieving streaming availability.",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="TMDB is currently unreachable.",
        ) from exc
