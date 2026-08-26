import logging

from sentry_sdk import capture_exception
from sqlalchemy.orm import Session as DBSession

from app.ingestion.analysis import analyze_transcript
from app.ingestion.bible_reference import BibleReferenceParseError
from app.ingestion.chunking import chunk_transcript
from app.ingestion.embeddings import embed_chunks
from app.ingestion.youtube import get_transcript
from app.models.processing_job import ProcessingJob
from app.models.sermon import ProcessingStatus, Sermon
from app.models.sermon_analysis import SermonAnalysis
from app.models.sermon_chunk import SermonChunk
from app.repositories.ingestion_repository import IngestionRepository

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


def _run_pipeline(sermon: Sermon) -> tuple[list[dict], object, list[list[float]]]:
    """Fetch, chunk, analyze, and embed. Raises on transcript failure.

    Pure sequencing over already-deep modules (youtube/chunking/analysis/
    embeddings) - no decisions made here, so this stays a plain function
    rather than living on IngestionService.
    """
    snippets = get_transcript(sermon.youtube_url)
    sermon.transcript = " ".join(s["text"] for s in snippets)

    chunks = chunk_transcript(snippets)
    analysis_result = analyze_transcript(sermon.transcript)  # ty: ignore[invalid-argument-type]
    embeddings = embed_chunks([c["text"] for c in chunks])
    return chunks, analysis_result, embeddings


class IngestionService:
    """Business rules for turning a pending Sermon into a fully analyzed
    one: retry limits, the pending/processing/completed/failed state
    machine, and idempotent persistence of analysis/chunks/taxonomy.

    Deliberately decoupled from Celery - this is what "ingesting a sermon"
    means, not how it's scheduled. `run` is the single entry point, callable
    from a Celery task, an admin retry endpoint, or a test, identically.
    Delegates data access to IngestionRepository and owns the transaction
    boundary (commit) around each state change.
    """

    def __init__(self, db: DBSession, repo: IngestionRepository):
        self._db = db
        self._repo = repo

    def _persist_results(
        self,
        sermon: Sermon,
        chunks: list[dict],
        analysis_result,
        embeddings: list[list[float]],
    ) -> None:
        if not self._repo.has_analysis(sermon.id):
            self._repo.add_analysis(
                SermonAnalysis(
                    sermon_id=sermon.id,
                    summary=analysis_result.summary,
                    key_teachings=analysis_result.key_teachings,
                    action_points=analysis_result.action_points,
                    reflection_questions=analysis_result.reflection_questions,
                    model_version="v1",
                )
            )

        if not self._repo.has_chunks(sermon.id):
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
                self._repo.add_chunk(
                    SermonChunk(
                        sermon_id=sermon.id,
                        chunk_index=i,
                        text=chunk["text"],
                        start_timestamp=int(chunk["start_timestamp"]),
                        end_timestamp=int(chunk["end_timestamp"]),
                        embedding=embedding,
                    )
                )

        for theme_name in analysis_result.themes:
            theme = self._repo.get_or_create_theme(theme_name)
            if theme not in sermon.themes:
                sermon.themes.append(theme)

        for ref_text in analysis_result.bible_references:
            try:
                ref = self._repo.get_or_create_bible_reference(ref_text)
            except BibleReferenceParseError:
                logger.warning(
                    "Skipping unparseable Bible reference %r for sermon %s",
                    ref_text,
                    sermon.id,
                )
                continue
            if ref not in sermon.bible_references:
                sermon.bible_references.append(ref)

    def _mark_failed(self, sermon: Sermon, job: ProcessingJob, error: Exception) -> None:
        job.attempt_count += 1
        job.error_message = str(error)
        sermon.status = ProcessingStatus.FAILED
        sermon.failure_reason = str(error)
        self._db.commit()

        logger.error(
            "Ingestion failed for sermon %s (attempt %d): %s",
            sermon.id,
            job.attempt_count,
            error,
            exc_info=error,
        )
        capture_exception(error)

    def run(self, sermon_id: str) -> None:
        """Run the full ingestion pipeline for a sermon and persist the
        result. A no-op if the sermon has already exhausted MAX_ATTEMPTS.
        Idempotent: safe to call again for a sermon that already has
        analysis/chunks (won't duplicate them).
        """
        sermon = self._repo.get_sermon(sermon_id)  # ty: ignore[invalid-argument-type]
        job = self._repo.get_or_create_job(sermon.id)

        if job.attempt_count >= MAX_ATTEMPTS:
            return

        sermon.status = ProcessingStatus.PROCESSING
        self._db.commit()

        try:
            chunks, analysis_result, embeddings = _run_pipeline(sermon)
        except Exception as e:
            self._mark_failed(sermon, job, e)
            return

        self._persist_results(sermon, chunks, analysis_result, embeddings)

        sermon.status = ProcessingStatus.COMPLETED
        self._db.commit()
