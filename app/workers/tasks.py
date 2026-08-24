from app.database import get_db_session
from app.repositories.ingestion_repository import IngestionRepository
from app.services.ingestion_service import IngestionService
from app.workers.celery_app import celery_app


@celery_app.task
def process_sermon(sermon_id: str) -> None:
    db = get_db_session()
    try:
        IngestionService(db, IngestionRepository(db)).run(sermon_id)
    finally:
        db.close()
