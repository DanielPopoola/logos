from app.database import get_db_session
from app.ingestion.analysis import analyze_transcript
from app.ingestion.chunking import chunk_transcript
from app.ingestion.embeddings import embed_chunks
from app.ingestion.youtube import get_transcript
from app.models.processing_job import ProcessingJob
from app.models.sermon import ProcessingStatus, Sermon
from app.models.sermon_analysis import SermonAnalysis
from app.models.sermon_chunk import SermonChunk
from app.models.taxonomy import BibleReference, Theme
from app.workers.celery_app import celery_app

MAX_ATTEMPTS = 3


def _get_or_create_theme(db, name: str) -> Theme:
    theme = db.query(Theme).filter_by(name=name).first()
    if theme is None:
        theme = Theme(name=name)
        db.add(theme)
        db.flush()
    return theme


def _get_or_create_bible_reference(db, display_text: str) -> BibleReference:
    ref = db.query(BibleReference).filter_by(display_text=display_text).first()
    if ref is None:
        book, rest = display_text.split(" ", 1)
        chapter_part = rest.split(":")[0]
        ref = BibleReference(book=book, chapter=int(chapter_part), display_text=display_text)
        db.add(ref)
        db.flush()
    return ref


def _get_or_create_job(db, sermon_id: str) -> ProcessingJob:
    job = db.query(ProcessingJob).filter_by(sermon_id=sermon_id).first()
    if job is None:
        job = ProcessingJob(sermon_id=sermon_id)
        db.add(job)
        db.flush()
    return job


def _run_pipeline(sermon: Sermon) -> tuple[list[dict], object, list[list[float]]]:
    """Fetch, chunk, analyze, and embed. Raises on transcript failure."""
    snippets = get_transcript(sermon.youtube_url)
    sermon.transcript = " ".join(s["text"] for s in snippets)

    chunks = chunk_transcript(snippets)
    analysis_result = analyze_transcript(sermon.transcript)  # ty: ignore[invalid-argument-type]
    embeddings = embed_chunks([c["text"] for c in chunks])
    return chunks, analysis_result, embeddings


def _persist_results(
    db, sermon: Sermon, chunks: list[dict], analysis_result, embeddings: list[list[float]]
) -> None:
    if db.query(SermonAnalysis).filter_by(sermon_id=sermon.id).first() is None:
        db.add(
            SermonAnalysis(
                sermon_id=sermon.id,
                summary=analysis_result.summary,
                key_teachings=analysis_result.key_teachings,
                action_points=analysis_result.action_points,
                reflection_questions=analysis_result.reflection_questions,
                model_version="v1",
            )
        )

    if db.query(SermonChunk).filter_by(sermon_id=sermon.id).count() == 0:
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
            db.add(
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
        theme = _get_or_create_theme(db, theme_name)
        if theme not in sermon.themes:
            sermon.themes.append(theme)

    for ref_text in analysis_result.bible_references:
        ref = _get_or_create_bible_reference(db, ref_text)
        if ref not in sermon.bible_references:
            sermon.bible_references.append(ref)


def _mark_failed(db, sermon: Sermon, job: ProcessingJob, error: Exception) -> None:
    job.attempt_count += 1
    job.error_message = str(error)
    sermon.status = ProcessingStatus.FAILED
    sermon.failure_reason = str(error)
    db.commit()


@celery_app.task
def process_sermon(sermon_id: str) -> None:
    db = get_db_session()
    try:
        sermon = db.query(Sermon).filter_by(id=sermon_id).one()
        job = _get_or_create_job(db, sermon.id)

        if job.attempt_count >= MAX_ATTEMPTS:
            return

        sermon.status = ProcessingStatus.PROCESSING
        db.commit()

        try:
            chunks, analysis_result, embeddings = _run_pipeline(sermon)
        except Exception as e:
            _mark_failed(db, sermon, job, e)
            return

        _persist_results(db, sermon, chunks, analysis_result, embeddings)

        sermon.status = "completed"
        db.commit()
    finally:
        db.close()
