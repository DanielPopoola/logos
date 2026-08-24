from unittest.mock import patch

from app.ingestion.analysis import SermonAnalysisResult
from app.models.processing_job import ProcessingJob
from app.models.sermon import Sermon
from app.models.sermon_analysis import SermonAnalysis
from app.models.sermon_chunk import SermonChunk
from app.models.taxonomy import BibleReference, Theme
from app.repositories.ingestion_repository import IngestionRepository
from app.services.ingestion_service import MAX_ATTEMPTS, IngestionService

MOCK_SNIPPETS = [{"text": "hello world " * 30, "start": 0.0, "duration": 10.0}]
MOCK_CHUNKS = [{"text": "hello world", "start_timestamp": 0.0, "end_timestamp": 10.0}]
MOCK_ANALYSIS = SermonAnalysisResult(
    summary="A summary.",
    key_teachings=["Teaching one"],
    themes=["faith", "trust"],
    bible_references=["Romans 8:28"],
    action_points=["Pray more"],
    reflection_questions=["What did you learn?"],
)
MOCK_EMBEDDINGS = [[0.1] * 768]


def _service(db_session) -> IngestionService:
    return IngestionService(db_session, IngestionRepository(db_session))


def _pending_sermon(db_session, video_id="ING1"):
    sermon = Sermon(youtube_video_id=video_id, youtube_url=f"https://youtu.be/{video_id}")
    db_session.add(sermon)
    db_session.commit()
    return sermon


def test_run_produces_correct_rows_on_success(db_session):
    service = _service(db_session)
    sermon = _pending_sermon(db_session)

    with (
        patch("app.services.ingestion_service.get_transcript", return_value=MOCK_SNIPPETS),
        patch("app.services.ingestion_service.chunk_transcript", return_value=MOCK_CHUNKS),
        patch("app.services.ingestion_service.analyze_transcript", return_value=MOCK_ANALYSIS),
        patch("app.services.ingestion_service.embed_chunks", return_value=MOCK_EMBEDDINGS),
    ):
        service.run(str(sermon.id))

    db_session.refresh(sermon)
    assert sermon.status == "completed"

    analysis = db_session.query(SermonAnalysis).filter_by(sermon_id=sermon.id).one()
    assert analysis.summary == "A summary."

    chunks = db_session.query(SermonChunk).filter_by(sermon_id=sermon.id).all()
    assert len(chunks) == 1
    assert chunks[0].embedding is not None

    theme_names = {
        t.name for t in db_session.query(Theme).join(Theme.sermons).filter(Sermon.id == sermon.id)
    }
    assert theme_names == {"faith", "trust"}

    ref_texts = {
        r.display_text
        for r in db_session.query(BibleReference)
        .join(BibleReference.sermons)
        .filter(Sermon.id == sermon.id)
    }
    assert ref_texts == {"Romans 8:28"}


def test_run_is_idempotent_on_retry(db_session):
    service = _service(db_session)
    sermon = _pending_sermon(db_session)

    with (
        patch("app.services.ingestion_service.get_transcript", return_value=MOCK_SNIPPETS),
        patch("app.services.ingestion_service.chunk_transcript", return_value=MOCK_CHUNKS),
        patch("app.services.ingestion_service.analyze_transcript", return_value=MOCK_ANALYSIS),
        patch("app.services.ingestion_service.embed_chunks", return_value=MOCK_EMBEDDINGS),
    ):
        service.run(str(sermon.id))
        service.run(str(sermon.id))

    assert db_session.query(SermonAnalysis).filter_by(sermon_id=sermon.id).count() == 1
    theme_count = db_session.query(Theme).filter_by(name="faith").count()
    assert theme_count == 1


def test_run_marks_failed_with_reason_on_transcript_failure(db_session):
    service = _service(db_session)
    sermon = _pending_sermon(db_session)

    with patch(
        "app.services.ingestion_service.get_transcript",
        side_effect=Exception("No captions available"),
    ):
        service.run(str(sermon.id))

    db_session.refresh(sermon)
    assert sermon.status == "failed"
    assert "No captions available" in sermon.failure_reason

    job = db_session.query(ProcessingJob).filter_by(sermon_id=sermon.id).one()
    assert job.attempt_count == 1


def test_run_stops_retrying_beyond_max_attempts(db_session):
    service = _service(db_session)
    sermon = _pending_sermon(db_session)

    with patch(
        "app.services.ingestion_service.get_transcript",
        side_effect=Exception("No captions available"),
    ):
        for _ in range(5):  # exceeds MAX_ATTEMPTS
            service.run(str(sermon.id))

    job = db_session.query(ProcessingJob).filter_by(sermon_id=sermon.id).one()
    assert job.attempt_count == MAX_ATTEMPTS
    db_session.refresh(sermon)
    assert sermon.status == "failed"
