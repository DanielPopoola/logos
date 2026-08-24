import uuid
from unittest.mock import patch

import pytest

from app.models.processing_job import ProcessingJob
from app.models.sermon import ProcessingStatus, Sermon
from app.models.sermon_analysis import SermonAnalysis
from app.models.taxonomy import BibleReference, Theme
from app.models.user import User
from app.models.user_note import UserNote
from app.models.user_sermon import UserSermon
from app.repositories.note_repository import NoteRepository
from app.repositories.sermon_repository import SermonRepository
from app.services.sermon_service import (
    SUMMARY_EXCERPT_MAX_CHARS,
    SermonNotFoundError,
    SermonService,
)

YOUTUBE_URL = "https://www.youtube.com/watch?v=ABC123xyz45"
VIDEO_ID = "ABC123xyz45"


def _sermon_service(db_session) -> SermonService:
    return SermonService(db_session, SermonRepository(db_session), NoteRepository(db_session))


def _user(db_session, google_id="u1") -> User:
    user = User(google_id=google_id, email=f"{google_id}@example.com")
    db_session.add(user)
    db_session.commit()
    return user


def _completed_sermon(
    db_session, video_id: str, summary: str | None = None, title: str = "A Sermon"
) -> Sermon:
    sermon = Sermon(
        youtube_video_id=video_id,
        youtube_url=f"https://youtu.be/{video_id}",
        title=title,
        status=ProcessingStatus.COMPLETED,
    )
    db_session.add(sermon)
    db_session.flush()
    if summary is not None:
        db_session.add(SermonAnalysis(sermon_id=sermon.id, summary=summary, model_version="v1"))
    db_session.commit()
    return sermon


def _save_to_library(db_session, user: User, sermon: Sermon) -> None:
    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    db_session.commit()


# --- submit_sermon ---------------------------------------------------------


def test_new_video_creates_sermon_job_and_user_sermon_then_enqueues(db_session):
    service = _sermon_service(db_session)
    user = _user(db_session)

    with patch("app.services.sermon_service.process_sermon") as mock_task:
        result = service.submit_sermon(user, YOUTUBE_URL)

    assert result.status_code == 201
    assert result.sermon.status == ProcessingStatus.PENDING

    sermon = db_session.query(Sermon).filter_by(youtube_video_id=VIDEO_ID).one()
    assert db_session.query(ProcessingJob).filter_by(sermon_id=sermon.id).count() == 1
    assert db_session.query(UserSermon).filter_by(user_id=user.id, sermon_id=sermon.id).count() == 1
    mock_task.delay.assert_called_once_with(str(sermon.id))


def test_completed_video_new_to_user_only_creates_user_sermon(db_session):
    service = _sermon_service(db_session)
    owner = _user(db_session, "owner")
    newcomer = _user(db_session, "newcomer")

    with patch("app.services.sermon_service.process_sermon"):
        service.submit_sermon(owner, YOUTUBE_URL)

    sermon = db_session.query(Sermon).filter_by(youtube_video_id=VIDEO_ID).one()
    sermon.status = ProcessingStatus.COMPLETED
    db_session.commit()

    with patch("app.services.sermon_service.process_sermon") as mock_task:
        result = service.submit_sermon(newcomer, YOUTUBE_URL)

    assert result.status_code == 200
    assert db_session.query(Sermon).filter_by(youtube_video_id=VIDEO_ID).count() == 1
    assert db_session.query(UserSermon).filter_by(user_id=newcomer.id, sermon_id=sermon.id).count() == 1
    mock_task.delay.assert_not_called()


def test_video_already_in_users_library_returns_existing_no_duplicate(db_session):
    service = _sermon_service(db_session)
    user = _user(db_session)

    with patch("app.services.sermon_service.process_sermon"):
        first = service.submit_sermon(user, YOUTUBE_URL)
        second = service.submit_sermon(user, YOUTUBE_URL)

    assert second.status_code == 200
    assert second.sermon.id == first.sermon.id
    sermon = db_session.query(Sermon).filter_by(youtube_video_id=VIDEO_ID).one()
    assert db_session.query(UserSermon).filter_by(sermon_id=sermon.id).count() == 1


def test_video_still_processing_elsewhere_and_new_to_user_returns_409(db_session):
    service = _sermon_service(db_session)
    owner = _user(db_session, "owner")
    newcomer = _user(db_session, "newcomer")

    with patch("app.services.sermon_service.process_sermon"):
        service.submit_sermon(owner, YOUTUBE_URL)

    with patch("app.services.sermon_service.process_sermon") as mock_task:
        result = service.submit_sermon(newcomer, YOUTUBE_URL)

    assert result.status_code == 409
    mock_task.delay.assert_not_called()
    sermon = db_session.query(Sermon).filter_by(youtube_video_id=VIDEO_ID).one()
    assert db_session.query(UserSermon).filter_by(user_id=newcomer.id, sermon_id=sermon.id).count() == 0


def test_failed_video_new_to_user_resets_to_pending_and_retries(db_session):
    service = _sermon_service(db_session)
    owner = _user(db_session, "owner")
    newcomer = _user(db_session, "newcomer")

    with patch("app.services.sermon_service.process_sermon"):
        service.submit_sermon(owner, YOUTUBE_URL)

    sermon = db_session.query(Sermon).filter_by(youtube_video_id=VIDEO_ID).one()
    sermon.status = ProcessingStatus.FAILED
    sermon.failure_reason = "No captions available"
    job = db_session.query(ProcessingJob).filter_by(sermon_id=sermon.id).one()
    job.attempt_count = 3
    job.error_message = "No captions available"
    db_session.commit()

    with patch("app.services.sermon_service.process_sermon") as mock_task:
        result = service.submit_sermon(newcomer, YOUTUBE_URL)

    assert result.status_code == 202
    db_session.refresh(sermon)
    assert sermon.status == ProcessingStatus.PENDING
    assert sermon.failure_reason is None
    db_session.refresh(job)
    assert job.attempt_count == 0
    assert job.error_message is None
    mock_task.delay.assert_called_once_with(str(sermon.id))
    assert db_session.query(UserSermon).filter_by(user_id=newcomer.id, sermon_id=sermon.id).count() == 1


def test_unparseable_url_raises_before_touching_db(db_session):
    service = _sermon_service(db_session)
    user = _user(db_session)

    with pytest.raises(ValueError, match="Could not extract video ID"):
        service.submit_sermon(user, "https://example.com/not-youtube")

    assert db_session.query(Sermon).count() == 0


# --- get_library ------------------------------------------------------------


def test_only_returns_current_users_sermons(db_session):
    service = _sermon_service(db_session)
    owner = _user(db_session, "owner")
    other = _user(db_session, "other")
    sermon = _completed_sermon(db_session, "LIB1", "Summary text")
    _save_to_library(db_session, owner, sermon)

    result = service.get_library(other, page=1, page_size=20, theme=None)

    assert result.total == 0
    assert result.items == []


def test_returns_only_this_users_sermons_not_others(db_session):
    service = _sermon_service(db_session)
    owner = _user(db_session, "owner")
    other = _user(db_session, "other")
    mine = _completed_sermon(db_session, "LIB2", "Mine")
    theirs = _completed_sermon(db_session, "LIB3", "Theirs")
    _save_to_library(db_session, owner, mine)
    _save_to_library(db_session, other, theirs)

    result = service.get_library(owner, page=1, page_size=20, theme=None)

    assert result.total == 1
    assert result.items[0].id == mine.id


def test_summary_excerpt_is_truncated_and_full_summary_not_leaked(db_session):
    service = _sermon_service(db_session)
    user = _user(db_session)
    long_summary = "word " * 100  # far exceeds SUMMARY_EXCERPT_MAX_CHARS
    sermon = _completed_sermon(db_session, "LIB4", long_summary)
    _save_to_library(db_session, user, sermon)

    result = service.get_library(user, page=1, page_size=20, theme=None)

    excerpt = result.items[0].summary_excerpt
    assert len(excerpt) <= SUMMARY_EXCERPT_MAX_CHARS  # ty: ignore[invalid-argument-type]
    assert excerpt != long_summary


def test_theme_filter_returns_only_matching_sermons(db_session):
    service = _sermon_service(db_session)
    user = _user(db_session)
    faith_theme = Theme(name="faith")
    prayer_theme = Theme(name="prayer")
    db_session.add_all([faith_theme, prayer_theme])
    db_session.commit()

    faith_sermon = _completed_sermon(db_session, "LIB5", "About faith")
    prayer_sermon = _completed_sermon(db_session, "LIB6", "About prayer")
    faith_sermon.themes.append(faith_theme)
    prayer_sermon.themes.append(prayer_theme)
    db_session.commit()
    _save_to_library(db_session, user, faith_sermon)
    _save_to_library(db_session, user, prayer_sermon)

    result = service.get_library(user, page=1, page_size=20, theme="faith")

    assert result.total == 1
    assert result.items[0].id == faith_sermon.id


def test_pagination_returns_correct_total_and_page_slice(db_session):
    service = _sermon_service(db_session)
    user = _user(db_session)
    for i in range(5):
        sermon = _completed_sermon(db_session, f"LIB7{i}", f"Summary {i}")
        _save_to_library(db_session, user, sermon)

    page_1 = service.get_library(user, page=1, page_size=2, theme=None)
    page_2 = service.get_library(user, page=2, page_size=2, theme=None)

    assert page_1.total == 5
    assert len(page_1.items) == 2
    assert len(page_2.items) == 2
    assert {i.id for i in page_1.items}.isdisjoint({i.id for i in page_2.items})


def test_sorted_by_most_recently_saved_first(db_session):
    import time

    service = _sermon_service(db_session)
    user = _user(db_session)
    first = _completed_sermon(db_session, "LIB8A", "First")
    _save_to_library(db_session, user, first)
    time.sleep(0.01)
    second = _completed_sermon(db_session, "LIB8B", "Second")
    _save_to_library(db_session, user, second)

    result = service.get_library(user, page=1, page_size=20, theme=None)

    assert result.items[0].id == second.id
    assert result.items[1].id == first.id


# --- get_sermon_detail --------------------------------------------------------


def test_completed_sermon_in_library_returns_full_detail(db_session):
    service = _sermon_service(db_session)
    user = _user(db_session)
    sermon = Sermon(
        youtube_video_id="DET1",
        youtube_url="https://youtu.be/DET1",
        title="A Sermon",
        speaker="Pastor X",
        status=ProcessingStatus.COMPLETED,
    )
    db_session.add(sermon)
    db_session.flush()
    db_session.add(
        SermonAnalysis(
            sermon_id=sermon.id,
            summary="A summary.",
            key_teachings=["Teaching one"],
            action_points=["Pray more"],
            reflection_questions=["What did you learn?"],
            model_version="v1",
        )
    )
    theme = Theme(name="faith")
    ref = BibleReference(book="Romans", chapter=8, verse_start=28, display_text="Romans 8:28")
    db_session.add_all([theme, ref])
    db_session.commit()
    sermon.themes.append(theme)
    sermon.bible_references.append(ref)
    db_session.commit()
    _save_to_library(db_session, user, sermon)
    db_session.add(UserNote(user_id=user.id, sermon_id=sermon.id, content="My reflection"))
    db_session.commit()

    result = service.get_sermon_detail(user, sermon.id)

    assert result.id == sermon.id
    assert result.status == ProcessingStatus.COMPLETED
    assert result.analysis is not None
    assert result.analysis.summary == "A summary."
    assert result.themes == ["faith"]
    assert result.bible_references == ["Romans 8:28"]
    assert len(result.notes) == 1
    assert result.notes[0].content == "My reflection"


def test_still_processing_sermon_returns_null_analysis(db_session):
    service = _sermon_service(db_session)
    user = _user(db_session)
    sermon = Sermon(
        youtube_video_id="DET2",
        youtube_url="https://youtu.be/DET2",
        status=ProcessingStatus.PROCESSING,
    )
    db_session.add(sermon)
    db_session.commit()
    _save_to_library(db_session, user, sermon)

    result = service.get_sermon_detail(user, sermon.id)

    assert result.status == ProcessingStatus.PROCESSING
    assert result.analysis is None


def test_sermon_not_in_users_library_raises_not_found(db_session):
    service = _sermon_service(db_session)
    owner = _user(db_session, "owner")
    other = _user(db_session, "other")
    sermon = Sermon(
        youtube_video_id="DET3",
        youtube_url="https://youtu.be/DET3",
        status=ProcessingStatus.COMPLETED,
    )
    db_session.add(sermon)
    db_session.commit()
    _save_to_library(db_session, owner, sermon)

    with pytest.raises(SermonNotFoundError):
        service.get_sermon_detail(other, sermon.id)


def test_nonexistent_sermon_id_raises_same_not_found_error(db_session):
    service = _sermon_service(db_session)
    user = _user(db_session)

    with pytest.raises(SermonNotFoundError):
        service.get_sermon_detail(user, uuid.uuid4())


# --- delete_from_library -----------------------------------------------------


def test_deletes_current_users_user_sermon_row(db_session):
    service = _sermon_service(db_session)
    user = _user(db_session)
    sermon = _completed_sermon(db_session, "DEL1")
    _save_to_library(db_session, user, sermon)

    service.delete_from_library(user, sermon.id)

    assert db_session.query(UserSermon).filter_by(user_id=user.id, sermon_id=sermon.id).count() == 0


def test_canonical_sermon_survives_deletion(db_session):
    service = _sermon_service(db_session)
    user = _user(db_session)
    sermon = _completed_sermon(db_session, "DEL2")
    _save_to_library(db_session, user, sermon)

    service.delete_from_library(user, sermon.id)

    assert db_session.query(Sermon).filter_by(id=sermon.id).count() == 1


def test_other_users_library_entry_survives_deletion(db_session):
    service = _sermon_service(db_session)
    owner = _user(db_session, "owner")
    other = _user(db_session, "other")
    sermon = _completed_sermon(db_session, "DEL3")
    _save_to_library(db_session, owner, sermon)
    _save_to_library(db_session, other, sermon)

    service.delete_from_library(owner, sermon.id)

    assert db_session.query(UserSermon).filter_by(user_id=other.id, sermon_id=sermon.id).count() == 1
    assert db_session.query(UserSermon).filter_by(user_id=owner.id, sermon_id=sermon.id).count() == 0


def test_deleting_sermon_not_in_library_raises_not_found(db_session):
    service = _sermon_service(db_session)
    user = _user(db_session)
    sermon = _completed_sermon(db_session, "DEL4")
    # never saved to user's library

    with pytest.raises(SermonNotFoundError):
        service.delete_from_library(user, sermon.id)


def test_deleting_nonexistent_sermon_id_raises_not_found(db_session):
    service = _sermon_service(db_session)
    user = _user(db_session)

    with pytest.raises(SermonNotFoundError):
        service.delete_from_library(user, uuid.uuid4())
