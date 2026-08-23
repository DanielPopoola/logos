import pytest

from app.models.sermon import ProcessingStatus, Sermon
from app.models.sermon_analysis import SermonAnalysis
from app.models.taxonomy import BibleReference, Theme
from app.models.user import User
from app.models.user_note import UserNote
from app.models.user_sermon import UserSermon
from app.services.sermon_service import SermonNotFoundError, get_sermon_detail


def _user(db_session, google_id="u1") -> User:
    user = User(google_id=google_id, email=f"{google_id}@example.com")
    db_session.add(user)
    db_session.commit()
    return user


def _save_to_library(db_session, user: User, sermon: Sermon) -> None:
    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    db_session.commit()


def test_completed_sermon_in_library_returns_full_detail(db_session):
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

    result = get_sermon_detail(db_session, user, sermon.id)

    assert result.id == sermon.id
    assert result.status == ProcessingStatus.COMPLETED
    assert result.analysis is not None
    assert result.analysis.summary == "A summary."
    assert result.themes == ["faith"]
    assert result.bible_references == ["Romans 8:28"]
    assert len(result.notes) == 1
    assert result.notes[0].content == "My reflection"


def test_still_processing_sermon_returns_null_analysis(db_session):
    user = _user(db_session)
    sermon = Sermon(
        youtube_video_id="DET2",
        youtube_url="https://youtu.be/DET2",
        status=ProcessingStatus.PROCESSING,
    )
    db_session.add(sermon)
    db_session.commit()
    _save_to_library(db_session, user, sermon)

    result = get_sermon_detail(db_session, user, sermon.id)

    assert result.status == ProcessingStatus.PROCESSING
    assert result.analysis is None


def test_sermon_not_in_users_library_raises_not_found(db_session):
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
        get_sermon_detail(db_session, other, sermon.id)


def test_nonexistent_sermon_id_raises_same_not_found_error(db_session):
    import uuid

    user = _user(db_session)

    with pytest.raises(SermonNotFoundError):
        get_sermon_detail(db_session, user, uuid.uuid4())
