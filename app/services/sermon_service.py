import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session as DBSession

from app.ingestion.youtube import extract_video_id
from app.models.sermon import ProcessingStatus, Sermon
from app.models.user import User
from app.repositories.ingestion_repository import IngestionRepository
from app.repositories.note_repository import NoteRepository
from app.repositories.sermon_repository import SermonRepository
from app.text import truncate
from app.workers.tasks import process_sermon

logger = logging.getLogger(__name__)

SUMMARY_EXCERPT_MAX_CHARS = 150


class SermonNotFoundError(Exception):
    pass


class SermonNotRetryableError(Exception):
    pass


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


@dataclass
class SermonAnalysisOut:
    summary: str | None
    key_teachings: list[str]
    action_points: list[str]
    reflection_questions: list[str]


@dataclass
class NoteOut:
    id: uuid.UUID
    content: str
    created_at: object


@dataclass
class SermonDetail:
    id: uuid.UUID
    youtube_url: str
    title: str | None
    speaker: str | None
    duration_seconds: int | None
    status: ProcessingStatus
    failure_reason: str | None
    saved_at: object
    analysis: SermonAnalysisOut | None
    themes: list[str]
    bible_references: list[str]
    notes: list[NoteOut]


class SermonService:
    """Business rules for sermons: dedup-on-submit, library membership,
    ownership-scoped reads, and shaping persistence rows into service-facing
    types. Delegates data access to SermonRepository/NoteRepository and owns
    the transaction boundary (commit) around each operation.
    """

    def __init__(
        self,
        db: DBSession,
        sermons: SermonRepository,
        notes: NoteRepository,
        ingestion: IngestionRepository,
    ):
        self._db = db
        self._sermons = sermons
        self._notes = notes
        self._ingestion = ingestion

    def _reset_processing_job(self, sermon: Sermon) -> None:
        job = self._ingestion.get_or_create_job(sermon.id)
        job.attempt_count = 0
        job.error_message = None

    def _requeue_failed_sermon(self, sermon: Sermon) -> None:
        """Give a failed sermon a fresh attempt window and re-enqueue it.
        Shared by submit_sermon's failed-branch (retry via resubmission) and
        retry_ingestion (direct retry action) - both mean the same thing:
        "try this sermon again from scratch."
        """
        sermon.status = ProcessingStatus.PENDING
        sermon.failure_reason = None
        self._reset_processing_job(sermon)
        self._db.commit()
        process_sermon.delay(str(sermon.id))

    def submit_sermon(self, user: User, youtube_url: str) -> SubmitSermonResult:
        """Submit a YouTube sermon URL into the user's library.

        Dedupes on the canonical Sermon.youtube_video_id: a video is only
        ever transcribed/analyzed once, regardless of how many users submit
        it.

        Raises ValueError if the URL can't be parsed into a video ID.
        """
        video_id = extract_video_id(youtube_url)

        sermon = self._sermons.find_by_video_id(video_id)

        if sermon is None:
            sermon = Sermon(youtube_video_id=video_id, youtube_url=youtube_url)
            self._sermons.add(sermon)
            self._db.flush()
            self._ingestion.get_or_create_job(sermon.id)
            self._sermons.add_to_library(user.id, sermon.id)
            self._db.commit()
            process_sermon.delay(str(sermon.id))
            logger.info(
                "Sermon ingestion submitted",
                extra={"sermon_id": str(sermon.id), "user_id": str(user.id), "status_code": 201},
            )
            return SubmitSermonResult(sermon=sermon, status_code=201)

        if self._sermons.is_in_library(user.id, sermon.id):
            logger.info(
                "Sermon submission deduplicated",
                extra={"sermon_id": str(sermon.id), "user_id": str(user.id), "status_code": 200},
            )
            return SubmitSermonResult(sermon=sermon, status_code=200)

        if sermon.status == ProcessingStatus.COMPLETED:
            self._sermons.add_to_library(user.id, sermon.id)
            self._db.commit()
            logger.info(
                "Completed sermon added to library",
                extra={"sermon_id": str(sermon.id), "user_id": str(user.id)},
            )
            return SubmitSermonResult(sermon=sermon, status_code=200)

        if sermon.status == ProcessingStatus.FAILED:
            self._sermons.add_to_library(user.id, sermon.id)
            self._requeue_failed_sermon(sermon)
            logger.info(
                "Failed sermon requeued",
                extra={"sermon_id": str(sermon.id), "user_id": str(user.id)},
            )
            return SubmitSermonResult(sermon=sermon, status_code=202)

        # pending or processing elsewhere, not yet in this user's library
        logger.info(
            "Sermon submission conflicts with active ingestion",
            extra={"sermon_id": str(sermon.id), "user_id": str(user.id), "status_code": 409},
        )
        return SubmitSermonResult(sermon=sermon, status_code=409)

    @staticmethod
    def _truncate_summary(summary: str | None) -> str | None:
        if summary is None:
            return None
        return truncate(summary, SUMMARY_EXCERPT_MAX_CHARS)

    def get_library(self, user: User, page: int, page_size: int, theme: str | None) -> LibraryPage:
        """List the sermons in a user's library, most recently saved first.

        Scoped strictly to the current user's UserSermon rows - never
        returns another user's library entries, even for a sermon that's
        shared/canonical.
        """
        total = self._sermons.count_library(user.id, theme)
        rows = self._sermons.library_page(user.id, theme, page, page_size)

        items = [
            LibraryItem(
                id=sermon.id,
                title=sermon.title,
                speaker=sermon.speaker,
                status=sermon.status,
                duration_seconds=sermon.duration_seconds,
                summary_excerpt=self._truncate_summary(summary),
                themes=[t.name for t in sermon.themes],
                saved_at=saved_at,
            )
            for sermon, saved_at, summary in rows
        ]

        return LibraryPage(items=items, page=page, page_size=page_size, total=total)

    def _get_owned_sermon(self, user: User, sermon_id: uuid.UUID) -> tuple[Sermon, object]:
        """Fetch a sermon only if it's in the given user's library. Raises
        SermonNotFoundError otherwise - covers both "doesn't exist" and "not
        yours" with the same outcome, so a 404 never leaks existence.
        """
        row = self._sermons.get_owned_with_saved_at(user.id, sermon_id)
        if row is None:
            raise SermonNotFoundError(f"Sermon {sermon_id} not found in this user's library")
        return row

    def get_sermon_detail(self, user: User, sermon_id: uuid.UUID) -> SermonDetail:
        sermon, saved_at = self._get_owned_sermon(user, sermon_id)

        analysis_row = self._sermons.get_analysis(sermon.id)
        analysis = (
            SermonAnalysisOut(
                summary=analysis_row.summary,
                key_teachings=analysis_row.key_teachings or [],  # ty: ignore[invalid-argument-type]
                action_points=analysis_row.action_points or [],  # ty: ignore[invalid-argument-type]
                reflection_questions=analysis_row.reflection_questions or [],  # ty: ignore[invalid-argument-type]
            )
            if analysis_row is not None
            else None
        )

        notes = [
            NoteOut(id=n.id, content=n.content, created_at=n.created_at)
            for n in self._notes.get_for_sermon(user.id, sermon.id)
        ]

        return SermonDetail(
            id=sermon.id,
            youtube_url=sermon.youtube_url,
            title=sermon.title,
            speaker=sermon.speaker,
            duration_seconds=sermon.duration_seconds,
            status=sermon.status,
            failure_reason=sermon.failure_reason,
            saved_at=saved_at,
            analysis=analysis,
            themes=[t.name for t in sermon.themes],
            bible_references=[r.display_text for r in sermon.bible_references],
            notes=notes,
        )

    def delete_from_library(self, user: User, sermon_id: uuid.UUID) -> None:
        """Remove a sermon from the user's library.

        Only ever deletes the UserSermon join row - the canonical Sermon
        (and any other user's UserSermon pointing at it) is untouched, since
        the sermon is shared infrastructure, not something any single user
        owns.
        """
        removed = self._sermons.remove_from_library(user.id, sermon_id)
        if not removed:
            raise SermonNotFoundError(f"Sermon {sermon_id} not found in this user's library")
        self._db.commit()
        logger.info(
            "Sermon removed from library",
            extra={"sermon_id": str(sermon_id), "user_id": str(user.id)},
        )

    def retry_ingestion(self, user: User, sermon_id: uuid.UUID) -> Sermon:
        """Manually retry a failed sermon's ingestion.

        Ownership-scoped like every other sermon action - a user can only
        retry a sermon that's in their own library, and a sermon that
        doesn't exist or belongs to someone else's library raises the same
        SermonNotFoundError either way (no existence leak).

        Only meaningful for a sermon currently in FAILED status; retrying a
        pending/processing/completed sermon raises SermonNotRetryableError
        instead of silently no-op'ing or re-enqueueing redundant work.
        """
        sermon, _saved_at = self._get_owned_sermon(user, sermon_id)

        if sermon.status != ProcessingStatus.FAILED:
            raise SermonNotRetryableError(
                f"Sermon {sermon_id} is not in a failed state (status={sermon.status})"
            )

        self._requeue_failed_sermon(sermon)
        return sermon
