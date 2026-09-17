from fastapi import APIRouter

from app.models.media import StreamingServiceOption
from app.services.streaming_services import STREAMING_SERVICES

router = APIRouter(prefix="/api/v1", tags=["services"])


@router.get("/services", response_model=list[StreamingServiceOption])
async def get_services() -> list[StreamingServiceOption]:
    """Return services that can be selected by the desktop app or Mairon."""
    return [
        StreamingServiceOption(key=service.key, name=service.name)
        for service in STREAMING_SERVICES
    ]