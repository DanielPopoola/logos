from unittest.mock import patch

from app.ingestion.analysis import SermonAnalysisResult
from app.models.sermon import Sermon
from app.workers.tasks import process_sermon

MOCK_SNIPPETS = [{"text": "hello world " * 30, "start": 0.0, "duration": 10.0}]
MOCK_CHUNKS = [{"text": "hello world", "start_timestamp": 0.0, "end_timestamp": 10.0}]
MOCK_ANALYSIS = SermonAnalysisResult(
    summary="A summary.",
    key_teachings=["Teaching one"],
    themes=["faith"],
    bible_references=["Romans 8:28"],
    action_points=["Pray more"],
    reflection_questions=["What did you learn?"],
)
MOCK_EMBEDDINGS = [[0.1] * 768]


def test_process_sermon_delegates_to_ingestion_service_and_completes(db_session):
    """Thin sanity check that the Celery task is correctly wired to
    IngestionService - the actual ingestion business rules (idempotency,
    retry limits, failure handling) are covered directly against
    IngestionService in tests/services/test_ingestion_service.py, with no
    Celery involved.
    """
    sermon = Sermon(youtube_video_id="TASK1", youtube_url="https://youtu.be/TASK1")
    db_session.add(sermon)
    db_session.commit()

    with (
        patch("app.services.ingestion_service.get_transcript", return_value=MOCK_SNIPPETS),
        patch("app.services.ingestion_service.chunk_transcript", return_value=MOCK_CHUNKS),
        patch("app.services.ingestion_service.analyze_transcript", return_value=MOCK_ANALYSIS),
        patch("app.services.ingestion_service.embed_chunks", return_value=MOCK_EMBEDDINGS),
        patch("app.workers.tasks.get_db_session", return_value=db_session),
        patch.object(db_session, "close", lambda: None),
    ):
        process_sermon(str(sermon.id))

    db_session.refresh(sermon)
    assert sermon.status == "completed"
