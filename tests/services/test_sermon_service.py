from unittest.mock import patch

from app.models.processing_job import ProcessingJob
from app.models.sermon import ProcessingStatus, Sermon
from app.models.user import User
from app.models.user_sermon import UserSermon
from app.services.sermon_service import submit_sermon

YOUTUBE_URL = "https://www.youtube.com/watch?v=ABC123xyz45"
VIDEO_ID = "ABC123xyz45"


def _user(db_session, google_id="u1") -> User:
    user = User(google_id=google_id, email=f"{google_id}@example.com")
    db_session.add(user)
    db_session.commit()
    return user


def test_new_video_creates_sermon_job_and_user_sermon_then_enqueues(db_session):
    user = _user(db_session)

    with patch("app.services.sermon_service.process_sermon") as mock_task:
        result = submit_sermon(db_session, user, YOUTUBE_URL)

    assert result.status_code == 201
    assert result.sermon.status == ProcessingStatus.PENDING

    sermon = db_session.query(Sermon).filter_by(youtube_video_id=VIDEO_ID).one()
    assert db_session.query(ProcessingJob).filter_by(sermon_id=sermon.id).count() == 1
    assert db_session.query(UserSermon).filter_by(user_id=user.id, sermon_id=sermon.id).count() == 1
    mock_task.delay.assert_called_once_with(str(sermon.id))


def test_completed_video_new_to_user_only_creates_user_sermon(db_session):
    owner = _user(db_session, "owner")
    newcomer = _user(db_session, "newcomer")

    with patch("app.services.sermon_service.process_sermon"):
        submit_sermon(db_session, owner, YOUTUBE_URL)

    sermon = db_session.query(Sermon).filter_by(youtube_video_id=VIDEO_ID).one()
    sermon.status = ProcessingStatus.COMPLETED
    db_session.commit()

    with patch("app.services.sermon_service.process_sermon") as mock_task:
        result = submit_sermon(db_session, newcomer, YOUTUBE_URL)

    assert result.status_code == 200
    assert db_session.query(Sermon).filter_by(youtube_video_id=VIDEO_ID).count() == 1
    assert (
        db_session.query(UserSermon).filter_by(user_id=newcomer.id, sermon_id=sermon.id).count()
        == 1
    )
    mock_task.delay.assert_not_called()


def test_video_already_in_users_library_returns_existing_no_duplicate(db_session):
    user = _user(db_session)

    with patch("app.services.sermon_service.process_sermon"):
        first = submit_sermon(db_session, user, YOUTUBE_URL)
        second = submit_sermon(db_session, user, YOUTUBE_URL)

    assert second.status_code == 200
    assert second.sermon.id == first.sermon.id
    sermon = db_session.query(Sermon).filter_by(youtube_video_id=VIDEO_ID).one()
    assert db_session.query(UserSermon).filter_by(sermon_id=sermon.id).count() == 1


def test_video_still_processing_elsewhere_and_new_to_user_returns_409(db_session):
    owner = _user(db_session, "owner")
    newcomer = _user(db_session, "newcomer")

    with patch("app.services.sermon_service.process_sermon"):
        submit_sermon(db_session, owner, YOUTUBE_URL)

    with patch("app.services.sermon_service.process_sermon") as mock_task:
        result = submit_sermon(db_session, newcomer, YOUTUBE_URL)

    assert result.status_code == 409
    mock_task.delay.assert_not_called()
    sermon = db_session.query(Sermon).filter_by(youtube_video_id=VIDEO_ID).one()
    assert (
        db_session.query(UserSermon).filter_by(user_id=newcomer.id, sermon_id=sermon.id).count()
        == 0
    )


def test_failed_video_new_to_user_resets_to_pending_and_retries(db_session):
    owner = _user(db_session, "owner")
    newcomer = _user(db_session, "newcomer")

    with patch("app.services.sermon_service.process_sermon"):
        submit_sermon(db_session, owner, YOUTUBE_URL)

    sermon = db_session.query(Sermon).filter_by(youtube_video_id=VIDEO_ID).one()
    sermon.status = ProcessingStatus.FAILED
    sermon.failure_reason = "No captions available"
    job = db_session.query(ProcessingJob).filter_by(sermon_id=sermon.id).one()
    job.attempt_count = 3
    job.error_message = "No captions available"
    db_session.commit()

    with patch("app.services.sermon_service.process_sermon") as mock_task:
        result = submit_sermon(db_session, newcomer, YOUTUBE_URL)

    assert result.status_code == 202
    db_session.refresh(sermon)
    assert sermon.status == ProcessingStatus.PENDING
    assert sermon.failure_reason is None
    db_session.refresh(job)
    assert job.attempt_count == 0
    assert job.error_message is None
    mock_task.delay.assert_called_once_with(str(sermon.id))
    assert (
        db_session.query(UserSermon).filter_by(user_id=newcomer.id, sermon_id=sermon.id).count()
        == 1
    )


def test_unparseable_url_raises_before_touching_db(db_session):
    import pytest

    user = _user(db_session)

    with pytest.raises(ValueError, match="Could not extract video ID"):
        submit_sermon(db_session, user, "https://example.com/not-youtube")

    assert db_session.query(Sermon).count() == 0
