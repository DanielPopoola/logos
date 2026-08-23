import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.models.sermon import Sermon
from app.models.sermon_analysis import SermonAnalysis
from app.models.taxonomy import Theme, sermon_themes
from app.models.user_sermon import UserSermon


class SermonRepository:
    """Persistence access for Sermon and library membership (UserSermon).
    Query methods return raw SQLAlchemy rows/tuples - shaping that data into
    service-facing types (e.g. LibraryItem) is the service's job, not the
    repository's. Callers own the transaction (commit/rollback).
    """

    def __init__(self, db: DBSession):
        self._db = db

    def is_in_library(self, user_id: uuid.UUID, sermon_id: uuid.UUID) -> bool:
        return (
            self._db.query(UserSermon).filter_by(user_id=user_id, sermon_id=sermon_id).first()
            is not None
        )

    def find_by_video_id(self, video_id: str) -> Sermon | None:
        return self._db.query(Sermon).filter_by(youtube_video_id=video_id).first()

    def add(self, sermon: Sermon) -> None:
        self._db.add(sermon)

    def add_to_library(self, user_id: uuid.UUID, sermon_id: uuid.UUID) -> None:
        self._db.add(UserSermon(user_id=user_id, sermon_id=sermon_id))

    def remove_from_library(self, user_id: uuid.UUID, sermon_id: uuid.UUID) -> UserSermon | None:
        user_sermon = (
            self._db.query(UserSermon).filter_by(user_id=user_id, sermon_id=sermon_id).first()
        )
        if user_sermon is not None:
            self._db.delete(user_sermon)
        return user_sermon

    def get_owned_with_saved_at(
        self, user_id: uuid.UUID, sermon_id: uuid.UUID
    ) -> tuple[Sermon, object] | None:
        row = (
            self._db.query(Sermon, UserSermon.saved_at)
            .join(UserSermon, UserSermon.sermon_id == Sermon.id)
            .filter(Sermon.id == sermon_id, UserSermon.user_id == user_id)
            .first()
        )
        return row  # ty: ignore[invalid-return-type]

    def get_analysis(self, sermon_id: uuid.UUID) -> SermonAnalysis | None:
        return self._db.query(SermonAnalysis).filter_by(sermon_id=sermon_id).first()

    def _library_query(self, user_id: uuid.UUID, theme: str | None, *, count_only: bool):
        if count_only:
            query = self._db.query(func.count(Sermon.id.distinct()))
        else:
            query = self._db.query(Sermon, UserSermon.saved_at, SermonAnalysis.summary)

        query = (
            query.join(UserSermon, UserSermon.sermon_id == Sermon.id)
            .outerjoin(SermonAnalysis, SermonAnalysis.sermon_id == Sermon.id)
            .filter(UserSermon.user_id == user_id)
        )
        if theme is not None:
            query = (
                query.join(sermon_themes, sermon_themes.c.sermon_id == Sermon.id)
                .join(Theme, Theme.id == sermon_themes.c.theme_id)
                .filter(Theme.name == theme)
            )
        return query

    def count_library(self, user_id: uuid.UUID, theme: str | None) -> int:
        return self._library_query(user_id, theme, count_only=True).scalar()

    def library_page(
        self, user_id: uuid.UUID, theme: str | None, page: int, page_size: int
    ) -> list[tuple[Sermon, object, str | None]]:
        return (
            self._library_query(user_id, theme, count_only=False)
            .order_by(UserSermon.saved_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
