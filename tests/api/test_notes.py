import uuid
from datetime import UTC, datetime, timedelta

from app.models.sermon import ProcessingStatus, Sermon
from app.models.session import Session as SessionModel
from app.models.user import User
from app.models.user_sermon import UserSermon


def _authed_client(client, db_session, google_id="g1"):
    user = User(google_id=google_id, email=f"{google_id}@example.com")
    db_session.add(user)
    db_session.commit()
    session = SessionModel(
        token=f"token-{google_id}",
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(session)
    db_session.commit()
    client.cookies.set("session_token", f"token-{google_id}")
    return user


def _sermon_in_library(db_session, user, video_id):
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


def test_create_note_returns_201(client, db_session):
    user = _authed_client(client, db_session)
    sermon = _sermon_in_library(db_session, user, "NOTEHTTP1")

    response = client.post(f"/v1/sermons/{sermon.id}/notes", json={"content": "My reflection"})

    body = response.json()
    assert response.status_code == 201
    assert body["data"]["content"] == "My reflection"


def test_create_note_on_sermon_not_in_library_returns_404(client, db_session):
    _authed_client(client, db_session)

    response = client.post(f"/v1/sermons/{uuid.uuid4()}/notes", json={"content": "hi"})

    assert response.status_code == 404


def test_patch_note_updates_content(client, db_session):
    user = _authed_client(client, db_session)
    sermon = _sermon_in_library(db_session, user, "NOTEHTTP2")
    created = client.post(f"/v1/sermons/{sermon.id}/notes", json={"content": "Original"})
    note_id = created.json()["data"]["id"]

    response = client.patch(f"/v1/notes/{note_id}", json={"content": "Updated"})

    body = response.json()
    assert response.status_code == 200
    assert body["data"]["content"] == "Updated"


def test_patch_note_by_non_owner_returns_404(client, db_session):
    owner = _authed_client(client, db_session, "owner")
    sermon = _sermon_in_library(db_session, owner, "NOTEHTTP3")
    created = client.post(f"/v1/sermons/{sermon.id}/notes", json={"content": "Mine"})
    note_id = created.json()["data"]["id"]

    _authed_client(client, db_session, "other")
    response = client.patch(f"/v1/notes/{note_id}", json={"content": "Hijacked"})

    assert response.status_code == 404


def test_delete_note_returns_204(client, db_session):
    user = _authed_client(client, db_session)
    sermon = _sermon_in_library(db_session, user, "NOTEHTTP4")
    created = client.post(f"/v1/sermons/{sermon.id}/notes", json={"content": "To delete"})
    note_id = created.json()["data"]["id"]

    response = client.delete(f"/v1/notes/{note_id}")

    assert response.status_code == 204


def test_delete_note_by_non_owner_returns_404(client, db_session):
    owner = _authed_client(client, db_session, "owner")
    sermon = _sermon_in_library(db_session, owner, "NOTEHTTP5")
    created = client.post(f"/v1/sermons/{sermon.id}/notes", json={"content": "Protected"})
    note_id = created.json()["data"]["id"]

    _authed_client(client, db_session, "other")
    response = client.delete(f"/v1/notes/{note_id}")

    assert response.status_code == 404


def test_notes_require_auth(client):
    response = client.post(f"/v1/sermons/{uuid.uuid4()}/notes", json={"content": "x"})
    assert response.status_code == 401

    response = client.patch(f"/v1/notes/{uuid.uuid4()}", json={"content": "x"})
    assert response.status_code == 401

    response = client.delete(f"/v1/notes/{uuid.uuid4()}")
    assert response.status_code == 401
