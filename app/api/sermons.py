import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_current_user
from app.database import get_db
from app.errors import AppException
from app.models.sermon import ProcessingStatus
from app.models.user import User
from app.schemas.response import APIResponse
from app.schemas.sermon import (
    LibraryPageOut,
    SermonDetailOut,
    SermonSubmissionOut,
    SubmitSermonRequest,
)
from app.services.sermon_service import (
    SermonNotFoundError,
    get_library,
    get_sermon_detail,
    submit_sermon,
)

router = APIRouter()


@router.post("", response_model=APIResponse[SermonSubmissionOut])
def create_sermon(
    body: SubmitSermonRequest,
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[DBSession, Depends(get_db)],
):
    try:
        result = submit_sermon(db, user, body.youtube_url)
    except ValueError as e:
        raise AppException(status_code=400, code="invalid_youtube_url", message=str(e)) from e

    response.status_code = result.status_code
    return APIResponse.ok(SermonSubmissionOut.model_validate(result.sermon, from_attributes=True))


@router.get("", response_model=APIResponse[LibraryPageOut])
def list_sermons(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[DBSession, Depends(get_db)],
    theme: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    result = get_library(db, user, page=page, page_size=page_size, theme=theme)
    return APIResponse.ok(LibraryPageOut.model_validate(result, from_attributes=True))


@router.get("/{sermon_id}")
def get_sermon(
    sermon_id: uuid.UUID,
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[DBSession, Depends(get_db)],
):
    try:
        detail = get_sermon_detail(db, user, sermon_id)
    except SermonNotFoundError as e:
        raise AppException(status_code=404, code="sermon_not_found", message=str(e)) from e

    if detail.status in (ProcessingStatus.PENDING, ProcessingStatus.PROCESSING):
        response.status_code = 202
        return APIResponse.ok({"id": detail.id, "status": detail.status, "analysis": None})

    return APIResponse.ok(SermonDetailOut.model_validate(detail, from_attributes=True))
