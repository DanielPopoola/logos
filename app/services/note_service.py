import logging
import uuid

from sqlalchemy.orm import Session as DBSession

from app.models.user import User
from app.models.user_note import UserNote
from app.repositories.note_repository import NoteRepository
from app.repositories.sermon_repository import SermonRepository

logger = logging.getLogger(__name__)


class NoteNotFoundError(Exception):
    """Raised when a note doesn't exist, or exists but isn't owned by the
    requesting user. Also raised when creating a note on a sermon that isn't
    in the user's library. Deliberately the same error for "doesn't exist"
    and "not yours" - callers must not be able to tell the two apart."""


class NoteService:
    """Business rules for user notes: ownership enforcement and the
    library-membership precondition for note creation. Delegates data
    access to NoteRepository/SermonRepository and owns the transaction
    boundary (commit) around each operation.
    """

    def __init__(self, db: DBSession, notes: NoteRepository, sermons: SermonRepository):
        self._db = db
        self._notes = notes
        self._sermons = sermons

    def _get_owned_note(self, user: User, note_id: uuid.UUID) -> UserNote:
        note = self._notes.get_owned_by_user(note_id, user.id)
        if note is None:
            raise NoteNotFoundError(f"Note {note_id} not found for this user")
        return note

    def create_note(self, user: User, sermon_id: uuid.UUID, content: str) -> UserNote:
        if not self._sermons.is_in_library(user.id, sermon_id):
            raise NoteNotFoundError(f"Sermon {sermon_id} not found in this user's library")

        note = UserNote(user_id=user.id, sermon_id=sermon_id, content=content)
        self._notes.add(note)
        self._db.commit()
        return note

    def update_note(self, user: User, note_id: uuid.UUID, content: str) -> UserNote:
        note = self._get_owned_note(user, note_id)
        note.content = content
        self._db.commit()
        return note

    def delete_note(self, user: User, note_id: uuid.UUID) -> None:
        note = self._get_owned_note(user, note_id)
        self._notes.delete(note)
        self._db.commit()
