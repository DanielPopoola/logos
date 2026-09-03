import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import get_current_user, get_note_service, get_sermon_service
from app.errors import AppException
from app.models.sermon import ProcessingStatus
from app.models.user import User
from app.schemas.response import APIResponse
from app.schemas.sermon import (
    CreateNoteRequest,
    LibraryPageOut,
    NoteCreateOut,
    SermonDetailOut,
    SermonSubmissionOut,
    SubmitSermonRequest,
)
from app.services.note_service import NoteNotFoundError, NoteService
from app.services.sermon_service import (
    SermonNotFoundError,
    SermonNotRetryableError,
    SermonService,
)

router = APIRouter()


@router.post("", response_model=APIResponse[SermonSubmissionOut])
def create_sermon(
    body: SubmitSermonRequest,
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    sermon_service: Annotated[SermonService, Depends(get_sermon_service)],
):
    try:
        result = sermon_service.submit_sermon(user, body.youtube_url)
    except ValueError as e:
        raise AppException(status_code=400, code="invalid_youtube_url", message=str(e)) from e

    response.status_code = result.status_code
    return APIResponse.ok(SermonSubmissionOut.model_validate(result.sermon, from_attributes=True))


@router.get("", response_model=APIResponse[LibraryPageOut])
def list_sermons(
    user: Annotated[User, Depends(get_current_user)],
    sermon_service: Annotated[SermonService, Depends(get_sermon_service)],
    theme: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    result = sermon_service.get_library(user, page=page, page_size=page_size, theme=theme)
    return APIResponse.ok(LibraryPageOut.model_validate(result, from_attributes=True))


@router.get("/{sermon_id}")
def get_sermon(
    sermon_id: uuid.UUID,
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    sermon_service: Annotated[SermonService, Depends(get_sermon_service)],
):
    try:
        detail = sermon_service.get_sermon_detail(user, sermon_id)
    except SermonNotFoundError as e:
        raise AppException(status_code=404, code="sermon_not_found", message=str(e)) from e

    if detail.status in (ProcessingStatus.PENDING, ProcessingStatus.PROCESSING):
        response.status_code = 202
        return APIResponse.ok({"id": detail.id, "status": detail.status, "analysis": None})

    return APIResponse.ok(SermonDetailOut.model_validate(detail, from_attributes=True))


@router.delete("/{sermon_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sermon(
    sermon_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    sermon_service: Annotated[SermonService, Depends(get_sermon_service)],
):
    try:
        sermon_service.delete_from_library(user, sermon_id)
    except SermonNotFoundError as e:
        raise AppException(status_code=404, code="sermon_not_found", message=str(e)) from e


@router.post("/{sermon_id}/retry", response_model=APIResponse[SermonSubmissionOut])
def retry_sermon(
    sermon_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    sermon_service: Annotated[SermonService, Depends(get_sermon_service)],
):
    try:
        sermon = sermon_service.retry_ingestion(user, sermon_id)
    except SermonNotFoundError as e:
        raise AppException(status_code=404, code="sermon_not_found", message=str(e)) from e
    except SermonNotRetryableError as e:
        raise AppException(status_code=409, code="sermon_not_retryable", message=str(e)) from e

    return APIResponse.ok(SermonSubmissionOut.model_validate(sermon, from_attributes=True))


@router.post(
    "/{sermon_id}/notes",
    status_code=status.HTTP_201_CREATED,
    response_model=APIResponse[NoteCreateOut],
)
def create_sermon_note(
    sermon_id: uuid.UUID,
    body: CreateNoteRequest,
    user: Annotated[User, Depends(get_current_user)],
    note_service: Annotated[NoteService, Depends(get_note_service)],
):
    try:
        note = note_service.create_note(user, sermon_id, body.content)
    except NoteNotFoundError as e:
        raise AppException(status_code=404, code="sermon_not_found", message=str(e)) from e

    return APIResponse.ok(NoteCreateOut.model_validate(note, from_attributes=True))
