import uuid

from sqlalchemy.orm import Session as DBSession

from app.models.user import User
from app.models.user_note import UserNote
from app.models.user_sermon import UserSermon


class NoteNotFoundError(Exception):
    """Raised when a note doesn't exist, or exists but isn't owned by the
    requesting user. Also raised when creating a note on a sermon that isn't
    in the user's library. Deliberately the same error for "doesn't exist"
    and "not yours" - callers must not be able to tell the two apart."""


def _is_sermon_in_library(db: DBSession, user: User, sermon_id: uuid.UUID) -> bool:
    return db.query(UserSermon).filter_by(user_id=user.id, sermon_id=sermon_id).first() is not None


def _get_owned_note(db: DBSession, user: User, note_id: uuid.UUID) -> UserNote:
    note = db.query(UserNote).filter_by(id=note_id, user_id=user.id).first()
    if note is None:
        raise NoteNotFoundError(f"Note {note_id} not found for this user")
    return note


def create_note(db: DBSession, user: User, sermon_id: uuid.UUID, content: str) -> UserNote:
    if not _is_sermon_in_library(db, user, sermon_id):
        raise NoteNotFoundError(f"Sermon {sermon_id} not found in this user's library")

    note = UserNote(user_id=user.id, sermon_id=sermon_id, content=content)
    db.add(note)
    db.commit()
    return note


def update_note(db: DBSession, user: User, note_id: uuid.UUID, content: str) -> UserNote:
    note = _get_owned_note(db, user, note_id)
    note.content = content
    db.commit()
    return note


def delete_note(db: DBSession, user: User, note_id: uuid.UUID) -> None:
    note = _get_owned_note(db, user, note_id)
    db.delete(note)
    db.commit()
