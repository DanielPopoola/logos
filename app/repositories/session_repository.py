from sqlalchemy.orm import Session as DBSession

from app.models.session import Session as SessionModel


class SessionRepository:
    """Persistence access for Session (opaque token -> user). No business
    rules (e.g. what counts as expired) live here, only data access
    mechanics. Callers own the transaction (commit/rollback).
    """

    def __init__(self, db: DBSession):
        self._db = db

    def find_by_token(self, token: str) -> SessionModel | None:
        return self._db.query(SessionModel).filter_by(token=token).first()

    def add(self, session: SessionModel) -> None:
        self._db.add(session)

    def delete_by_token(self, token: str) -> None:
        self._db.query(SessionModel).filter_by(token=token).delete()
