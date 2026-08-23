import uuid

from sqlalchemy.orm import Session as DBSession

from app.models.user_sermon import UserSermon


class SermonRepository:
    """Persistence access for Sermon and library membership (UserSermon).
    Grows as more services need sermon data access - only what's needed
    today is here.
    """

    def __init__(self, db: DBSession):
        self._db = db

    def is_in_library(self, user_id: uuid.UUID, sermon_id: uuid.UUID) -> bool:
        return (
            self._db.query(UserSermon).filter_by(user_id=user_id, sermon_id=sermon_id).first()
            is not None
        )
