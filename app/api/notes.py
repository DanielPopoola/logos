import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_current_user
from app.database import get_db
from app.errors import AppException
from app.models.user import User
from app.schemas.response import APIResponse
from app.schemas.sermon import NoteUpdateOut, UpdateNoteRequest
from app.services.note_service import NoteNotFoundError, delete_note, update_note

router = APIRouter()


@router.patch("/{note_id}", response_model=APIResponse[NoteUpdateOut])
def patch_note(
    note_id: uuid.UUID,
    body: UpdateNoteRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[DBSession, Depends(get_db)],
):
    try:
        note = update_note(db, user, note_id, body.content)
    except NoteNotFoundError as e:
        raise AppException(status_code=404, code="note_not_found", message=str(e)) from e

    return APIResponse.ok(NoteUpdateOut.model_validate(note, from_attributes=True))


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_note(
    note_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[DBSession, Depends(get_db)],
):
    try:
        delete_note(db, user, note_id)
    except NoteNotFoundError as e:
        raise AppException(status_code=404, code="note_not_found", message=str(e)) from e
