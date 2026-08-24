import uuid

from sqlalchemy.orm import Session as DBSession

from app.models.processing_job import ProcessingJob
from app.models.sermon import Sermon
from app.models.sermon_analysis import SermonAnalysis
from app.models.sermon_chunk import SermonChunk
from app.models.taxonomy import BibleReference, Theme


class IngestionRepository:
    """Persistence access for the ingestion pipeline: Sermon lifecycle
    fields, ProcessingJob bookkeeping, taxonomy find-or-create, and
    analysis/chunk idempotency checks. Separate from the API-facing
    SermonRepository - this serves the worker's questions (mark
    processing, has this already been analyzed), not the library's
    (paginate, filter by theme). Callers own the transaction (commit).
    """

    def __init__(self, db: DBSession):
        self._db = db

    def get_sermon(self, sermon_id: uuid.UUID) -> Sermon:
        return self._db.query(Sermon).filter_by(id=sermon_id).one()

    def get_or_create_job(self, sermon_id: uuid.UUID) -> ProcessingJob:
        job = self._db.query(ProcessingJob).filter_by(sermon_id=sermon_id).first()
        if job is None:
            job = ProcessingJob(sermon_id=sermon_id)
            self._db.add(job)
            self._db.flush()
        return job

    def get_or_create_theme(self, name: str) -> Theme:
        theme = self._db.query(Theme).filter_by(name=name).first()
        if theme is None:
            theme = Theme(name=name)
            self._db.add(theme)
            self._db.flush()
        return theme

    def get_or_create_bible_reference(self, display_text: str) -> BibleReference:
        ref = self._db.query(BibleReference).filter_by(display_text=display_text).first()
        if ref is None:
            book, rest = display_text.split(" ", 1)
            chapter_part = rest.split(":")[0]
            ref = BibleReference(book=book, chapter=int(chapter_part), display_text=display_text)
            self._db.add(ref)
            self._db.flush()
        return ref

    def has_analysis(self, sermon_id: uuid.UUID) -> bool:
        return self._db.query(SermonAnalysis).filter_by(sermon_id=sermon_id).first() is not None

    def add_analysis(self, analysis: SermonAnalysis) -> None:
        self._db.add(analysis)

    def has_chunks(self, sermon_id: uuid.UUID) -> bool:
        return self._db.query(SermonChunk).filter_by(sermon_id=sermon_id).first() is not None

    def add_chunk(self, chunk: SermonChunk) -> None:
        self._db.add(chunk)
