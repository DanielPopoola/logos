import logging
import uuid

from sqlalchemy.orm import Session as DBSession

from app.models.user import User
from app.models.user_note import UserNote
from app.repositories.note_repository import NoteRepository
from app.repositories.sermon_repository import SermonRepository

logger = logging.getLogger(__name__)


class NoteNotFoundError(Exception):
    pass


class NoteService:
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
        logger.info(
            "Note created",
            extra={"note_id": str(note.id), "sermon_id": str(sermon_id), "user_id": str(user.id)},
        )
        return note

    def update_note(self, user: User, note_id: uuid.UUID, content: str) -> UserNote:
        note = self._get_owned_note(user, note_id)
        note.content = content
        self._db.commit()
        logger.info("Note updated", extra={"note_id": str(note.id), "user_id": str(user.id)})
        return note

    def delete_note(self, user: User, note_id: uuid.UUID) -> None:
        note = self._get_owned_note(user, note_id)
        self._notes.delete(note)
        self._db.commit()
        logger.info("Note deleted", extra={"note_id": str(note.id), "user_id": str(user.id)})
