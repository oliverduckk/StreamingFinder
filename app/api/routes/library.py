from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from app.api.dependencies import get_library_repository
from app.models.media import (
    LibraryStatus,
    MediaLibraryEntry,
    MediaLibrarySaveRequest,
    MediaSearchResult,
    MediaType,
)
from app.repositories.library import MediaLibraryRepository

router = APIRouter(prefix="/api/v1/library", tags=["library"])


@router.get("", response_model=list[MediaLibraryEntry])
def list_library(
    status_filter: LibraryStatus | None = Query(default=None, alias="status"),
    favourite: bool | None = Query(default=None),
    library: MediaLibraryRepository = Depends(get_library_repository),
) -> list[MediaLibraryEntry]:
    return library.list(status=status_filter, favourite=favourite)


@router.get("/{media_type}/{tmdb_id}", response_model=MediaLibraryEntry)
def get_library_item(
    media_type: MediaType,
    tmdb_id: int = Path(gt=0),
    library: MediaLibraryRepository = Depends(get_library_repository),
) -> MediaLibraryEntry:
    entry = library.get(media_type, tmdb_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Media item is not in the library.")
    return entry


@router.put("/{media_type}/{tmdb_id}", response_model=MediaLibraryEntry)
def save_library_item(
    payload: MediaLibrarySaveRequest,
    media_type: MediaType,
    tmdb_id: int = Path(gt=0),
    library: MediaLibraryRepository = Depends(get_library_repository),
) -> MediaLibraryEntry:
    media = MediaSearchResult(
        tmdb_id=tmdb_id,
        media_type=media_type,
        title=payload.title,
        year=payload.year,
        overview=payload.overview,
        poster_path=payload.poster_path,
    )
    return library.upsert(media, payload.status, favourite=payload.favourite)


@router.delete("/{media_type}/{tmdb_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_library_item(
    media_type: MediaType,
    tmdb_id: int = Path(gt=0),
    library: MediaLibraryRepository = Depends(get_library_repository),
) -> Response:
    library.remove(media_type, tmdb_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
