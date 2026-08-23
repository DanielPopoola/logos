import uuid

from sqlalchemy.orm import Session as DBSession

from app.models.user import User


class UserRepository:
    def __init__(self, db: DBSession):
        self._db = db

    def find_by_google_id(self, google_id: str) -> User | None:
        return self._db.query(User).filter_by(google_id=google_id).first()

    def find_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._db.query(User).filter_by(id=user_id).first()

    def add(self, user: User) -> None:
        self._db.add(user)
