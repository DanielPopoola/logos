from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.models.sermon import ProcessingStatus, Sermon
from app.models.sermon_chunk import SermonChunk
from app.models.session import Session as SessionModel
from app.models.user import User
from app.models.user_sermon import UserSermon


def _authed_client(client, db_session):
    user = User(google_id="g1", email="g1@example.com")
    db_session.add(user)
    db_session.commit()
    session = SessionModel(
        token="valid-token", user_id=user.id, expires_at=datetime.now(UTC) + timedelta(days=1)
    )
    db_session.add(session)
    db_session.commit()
    client.cookies.set("session_token", "valid-token")
    return user


def _sermon_with_chunk(db_session, user, video_id="V1"):
    sermon = Sermon(
        youtube_video_id=video_id,
        youtube_url=f"https://youtu.be/{video_id}",
        status=ProcessingStatus.COMPLETED,
        title="Faith Under Fire",
        speaker="Pastor Jane",
    )
    db_session.add(sermon)
    db_session.flush()
    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    db_session.add(
        SermonChunk(
            sermon_id=sermon.id,
            chunk_index=0,
            text="on trusting God in hardship",
            start_timestamp=42,
            embedding=[0.1] * 768,
        )
    )
    db_session.commit()
    return sermon


def test_search_returns_matching_results(client, db_session):
    user = _authed_client(client, db_session)
    sermon = _sermon_with_chunk(db_session, user)

    with patch("app.services.search_service.embed_batch", return_value=[[0.1] * 768]):
        response = client.get("/v1/search", params={"q": "trusting God", "limit": 5})

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["results"][0]["sermon_id"] == str(sermon.id)
    assert body["data"]["results"][0]["matched_excerpt"] == "on trusting God in hardship"


def test_search_without_session_returns_401(client):
    response = client.get("/v1/search", params={"q": "anything"})

    assert response.status_code == 401


def test_search_missing_query_returns_422(client, db_session):
    _authed_client(client, db_session)

    response = client.get("/v1/search")

    assert response.status_code == 422
