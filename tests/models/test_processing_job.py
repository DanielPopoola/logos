from app.models.processing_job import ProcessingJob
from app.models.sermon import Sermon


def test_default_status_is_pending(db_session):
    sermon = Sermon(youtube_video_id="V6", youtube_url="https://youtu.be/V6")
    db_session.add(sermon)
    db_session.commit()

    job = ProcessingJob(sermon_id=sermon.id)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
