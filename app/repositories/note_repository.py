import uuid

from sqlalchemy.orm import Session as DBSession

from app.models.user_note import UserNote


class NoteRepository:
    """Persistence access for UserNote. Knows how to fetch, add, and delete
    notes - no business rules (ownership, validation) live here, only data
    access mechanics. Callers own the transaction (commit/rollback).
    """

    def __init__(self, db: DBSession):
        self._db = db

    def get_owned_by_user(self, note_id: uuid.UUID, user_id: uuid.UUID) -> UserNote | None:
        return self._db.query(UserNote).filter_by(id=note_id, user_id=user_id).first()

    def get_for_sermon(self, user_id: uuid.UUID, sermon_id: uuid.UUID) -> list[UserNote]:
        return (
            self._db.query(UserNote)
            .filter_by(user_id=user_id, sermon_id=sermon_id)
            .order_by(UserNote.created_at.desc())
            .all()
        )

    def add(self, note: UserNote) -> None:
        self._db.add(note)

    def delete(self, note: UserNote) -> None:
        self._db.delete(note)
