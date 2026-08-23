import uuid

import pytest

from app.models.sermon import ProcessingStatus, Sermon
from app.models.user import User
from app.models.user_note import UserNote
from app.models.user_sermon import UserSermon
from app.services.note_service import NoteNotFoundError, create_note, delete_note, update_note


def _user(db_session, google_id="u1") -> User:
    user = User(google_id=google_id, email=f"{google_id}@example.com")
    db_session.add(user)
    db_session.commit()
    return user


def _sermon_in_library(db_session, user: User, video_id: str) -> Sermon:
    sermon = Sermon(
        youtube_video_id=video_id,
        youtube_url=f"https://youtu.be/{video_id}",
        status=ProcessingStatus.COMPLETED,
    )
    db_session.add(sermon)
    db_session.flush()
    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    db_session.commit()
    return sermon


def test_create_note_persists_owned_by_current_user(db_session):
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "NOTE1")

    note = create_note(db_session, user, sermon.id, "My reflection")

    assert note.content == "My reflection"
    stored = db_session.query(UserNote).filter_by(id=note.id).one()
    assert stored.user_id == user.id
    assert stored.sermon_id == sermon.id


def test_create_note_on_sermon_not_in_library_raises_not_found(db_session):
    user = _user(db_session)
    sermon = Sermon(
        youtube_video_id="NOTE2",
        youtube_url="https://youtu.be/NOTE2",
        status=ProcessingStatus.COMPLETED,
    )
    db_session.add(sermon)
    db_session.commit()
    # never saved to user's library

    with pytest.raises(NoteNotFoundError):
        create_note(db_session, user, sermon.id, "My reflection")


def test_update_note_changes_content_for_owner(db_session):
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "NOTE3")
    note = create_note(db_session, user, sermon.id, "Original")

    updated = update_note(db_session, user, note.id, "Updated")

    assert updated.content == "Updated"
    db_session.refresh(note)
    assert note.content == "Updated"


def test_update_note_by_non_owner_raises_not_found(db_session):
    owner = _user(db_session, "owner")
    other = _user(db_session, "other")
    sermon = _sermon_in_library(db_session, owner, "NOTE4")
    note = create_note(db_session, owner, sermon.id, "Original")

    with pytest.raises(NoteNotFoundError):
        update_note(db_session, other, note.id, "Hijacked")

    db_session.refresh(note)
    assert note.content == "Original"


def test_update_nonexistent_note_raises_not_found(db_session):
    user = _user(db_session)

    with pytest.raises(NoteNotFoundError):
        update_note(db_session, user, uuid.uuid4(), "New content")


def test_delete_note_removes_it_for_owner(db_session):
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "NOTE5")
    note = create_note(db_session, user, sermon.id, "To delete")

    delete_note(db_session, user, note.id)

    assert db_session.query(UserNote).filter_by(id=note.id).count() == 0


def test_delete_note_by_non_owner_raises_not_found(db_session):
    owner = _user(db_session, "owner")
    other = _user(db_session, "other")
    sermon = _sermon_in_library(db_session, owner, "NOTE6")
    note = create_note(db_session, owner, sermon.id, "Protected")

    with pytest.raises(NoteNotFoundError):
        delete_note(db_session, other, note.id)

    assert db_session.query(UserNote).filter_by(id=note.id).count() == 1


def test_delete_nonexistent_note_raises_not_found(db_session):
    user = _user(db_session)

    with pytest.raises(NoteNotFoundError):
        delete_note(db_session, user, uuid.uuid4())
