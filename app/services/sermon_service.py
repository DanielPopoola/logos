from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.ingestion.youtube import extract_video_id
from app.models.processing_job import ProcessingJob
from app.models.sermon import ProcessingStatus, Sermon
from app.models.sermon_analysis import SermonAnalysis
from app.models.taxonomy import Theme, sermon_themes
from app.models.user import User
from app.models.user_sermon import UserSermon
from app.workers.tasks import process_sermon

SUMMARY_EXCERPT_MAX_CHARS = 150


@dataclass
class SubmitSermonResult:
    sermon: Sermon
    status_code: int


@dataclass
class LibraryItem:
    id: object
    title: str | None
    speaker: str | None
    status: ProcessingStatus
    duration_seconds: int | None
    summary_excerpt: str | None
    themes: list[str]
    saved_at: object


@dataclass
class LibraryPage:
    items: list[LibraryItem]
    page: int
    page_size: int
    total: int


def _create_sermon(db: DBSession, video_id: str, youtube_url: str) -> Sermon:
    sermon = Sermon(youtube_video_id=video_id, youtube_url=youtube_url)
    db.add(sermon)
    db.flush()
    db.add(ProcessingJob(sermon_id=sermon.id))
    return sermon


def _add_to_library(db: DBSession, user: User, sermon: Sermon) -> None:
    db.add(UserSermon(user_id=user.id, sermon_id=sermon.id))


def _is_in_library(db: DBSession, user: User, sermon: Sermon) -> bool:
    return db.query(UserSermon).filter_by(user_id=user.id, sermon_id=sermon.id).first() is not None


def _reset_processing_job(db: DBSession, sermon: Sermon) -> None:
    """A user-initiated retry is a fresh attempt window, distinct from the
    automatic retry loop inside process_sermon - without this, a video that
    already hit MAX_ATTEMPTS would silently no-op forever."""
    job = db.query(ProcessingJob).filter_by(sermon_id=sermon.id).first()
    if job is not None:
        job.attempt_count = 0
        job.error_message = None


def submit_sermon(db: DBSession, user: User, youtube_url: str) -> SubmitSermonResult:
    """Submit a YouTube sermon URL into the user's library.

    Dedupes on the canonical Sermon.youtube_video_id: a video is only ever
    transcribed/analyzed once, regardless of how many users submit it.

    Raises ValueError if the URL can't be parsed into a video ID.
    """
    video_id = extract_video_id(youtube_url)

    sermon = db.query(Sermon).filter_by(youtube_video_id=video_id).first()

    if sermon is None:
        sermon = _create_sermon(db, video_id, youtube_url)
        _add_to_library(db, user, sermon)
        db.commit()
        process_sermon.delay(str(sermon.id))
        return SubmitSermonResult(sermon=sermon, status_code=201)

    if _is_in_library(db, user, sermon):
        return SubmitSermonResult(sermon=sermon, status_code=200)

    if sermon.status == ProcessingStatus.COMPLETED:
        _add_to_library(db, user, sermon)
        db.commit()
        return SubmitSermonResult(sermon=sermon, status_code=200)

    if sermon.status == ProcessingStatus.FAILED:
        sermon.status = ProcessingStatus.PENDING
        sermon.failure_reason = None
        _reset_processing_job(db, sermon)
        _add_to_library(db, user, sermon)
        db.commit()
        process_sermon.delay(str(sermon.id))
        return SubmitSermonResult(sermon=sermon, status_code=202)

    # pending or processing elsewhere, not yet in this user's library
    return SubmitSermonResult(sermon=sermon, status_code=409)


def _truncate_summary(summary: str | None) -> str | None:
    if summary is None:
        return None
    if len(summary) <= SUMMARY_EXCERPT_MAX_CHARS:
        return summary
    return summary[:SUMMARY_EXCERPT_MAX_CHARS].rstrip() + "..."


def _base_library_query(db: DBSession, user: User, theme: str | None, *, count_only: bool = False):
    if count_only:
        query = db.query(func.count(Sermon.id.distinct()))
    else:
        query = db.query(Sermon, UserSermon.saved_at, SermonAnalysis.summary)

    query = (
        query.join(UserSermon, UserSermon.sermon_id == Sermon.id)
        .outerjoin(SermonAnalysis, SermonAnalysis.sermon_id == Sermon.id)
        .filter(UserSermon.user_id == user.id)
    )
    if theme is not None:
        query = (
            query.join(sermon_themes, sermon_themes.c.sermon_id == Sermon.id)
            .join(Theme, Theme.id == sermon_themes.c.theme_id)
            .filter(Theme.name == theme)
        )
    return query


def get_library(
    db: DBSession, user: User, page: int, page_size: int, theme: str | None
) -> LibraryPage:
    """List the sermons in a user's library, most recently saved first.

    Scoped strictly to the current user's UserSermon rows - never returns
    another user's library entries, even for a sermon that's shared/canonical.
    """
    total = _base_library_query(db, user, theme, count_only=True).scalar()

    rows = (
        _base_library_query(db, user, theme)
        .order_by(UserSermon.saved_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [
        LibraryItem(
            id=sermon.id,
            title=sermon.title,
            speaker=sermon.speaker,
            status=sermon.status,
            duration_seconds=sermon.duration_seconds,
            summary_excerpt=_truncate_summary(summary),
            themes=[t.name for t in sermon.themes],
            saved_at=saved_at,
        )
        for sermon, saved_at, summary in rows
    ]

    return LibraryPage(items=items, page=page, page_size=page_size, total=total)
