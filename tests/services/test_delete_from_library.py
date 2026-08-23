import uuid

import pytest

from app.models.sermon import ProcessingStatus, Sermon
from app.models.user import User
from app.models.user_sermon import UserSermon
from app.services.sermon_service import SermonNotFoundError, delete_from_library


def _user(db_session, google_id="u1") -> User:
    user = User(google_id=google_id, email=f"{google_id}@example.com")
    db_session.add(user)
    db_session.commit()
    return user


def _completed_sermon(db_session, video_id: str) -> Sermon:
    sermon = Sermon(
        youtube_video_id=video_id,
        youtube_url=f"https://youtu.be/{video_id}",
        status=ProcessingStatus.COMPLETED,
    )
    db_session.add(sermon)
    db_session.commit()
    return sermon


def _save_to_library(db_session, user: User, sermon: Sermon) -> None:
    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    db_session.commit()


def test_deletes_current_users_user_sermon_row(db_session):
    user = _user(db_session)
    sermon = _completed_sermon(db_session, "DEL1")
    _save_to_library(db_session, user, sermon)

    delete_from_library(db_session, user, sermon.id)

    assert db_session.query(UserSermon).filter_by(user_id=user.id, sermon_id=sermon.id).count() == 0


def test_canonical_sermon_survives_deletion(db_session):
    user = _user(db_session)
    sermon = _completed_sermon(db_session, "DEL2")
    _save_to_library(db_session, user, sermon)

    delete_from_library(db_session, user, sermon.id)

    assert db_session.query(Sermon).filter_by(id=sermon.id).count() == 1


def test_other_users_library_entry_survives_deletion(db_session):
    owner = _user(db_session, "owner")
    other = _user(db_session, "other")
    sermon = _completed_sermon(db_session, "DEL3")
    _save_to_library(db_session, owner, sermon)
    _save_to_library(db_session, other, sermon)

    delete_from_library(db_session, owner, sermon.id)

    assert (
        db_session.query(UserSermon).filter_by(user_id=other.id, sermon_id=sermon.id).count() == 1
    )
    assert (
        db_session.query(UserSermon).filter_by(user_id=owner.id, sermon_id=sermon.id).count() == 0
    )


def test_deleting_sermon_not_in_library_raises_not_found(db_session):
    user = _user(db_session)
    sermon = _completed_sermon(db_session, "DEL4")
    # never saved to user's library

    with pytest.raises(SermonNotFoundError):
        delete_from_library(db_session, user, sermon.id)


def test_deleting_nonexistent_sermon_id_raises_not_found(db_session):
    user = _user(db_session)

    with pytest.raises(SermonNotFoundError):
        delete_from_library(db_session, user, uuid.uuid4())
