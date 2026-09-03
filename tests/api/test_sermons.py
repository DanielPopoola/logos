from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.models.session import Session as SessionModel
from app.models.user import User

YOUTUBE_URL = "https://www.youtube.com/watch?v=ABC123xyz45"


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


def test_submit_new_sermon_returns_201_with_pending_status(client, db_session):
    _authed_client(client, db_session)

    with patch("app.services.sermon_service.process_sermon"):
        response = client.post("/v1/sermons", json={"youtube_url": YOUTUBE_URL})

    body = response.json()
    assert response.status_code == 201
    assert body["success"] is True
    assert body["data"]["status"] == "pending"


def test_submit_without_session_returns_401(client):
    response = client.post("/v1/sermons", json={"youtube_url": YOUTUBE_URL})

    assert response.status_code == 401


def test_submit_unparseable_url_returns_400(client, db_session):
    _authed_client(client, db_session)

    response = client.post("/v1/sermons", json={"youtube_url": "https://example.com/nope"})

    body = response.json()
    assert response.status_code == 400
    assert body["success"] is False
    assert body["error"]["code"] == "invalid_youtube_url"


def test_list_sermons_without_session_returns_401(client):
    response = client.get("/v1/sermons")

    assert response.status_code == 401


def test_list_sermons_returns_empty_page_for_new_user(client, db_session):
    _authed_client(client, db_session)

    response = client.get("/v1/sermons")

    body = response.json()
    assert response.status_code == 200
    assert body["data"]["items"] == []
    assert body["data"]["total"] == 0
    assert body["data"]["page"] == 1
    assert body["data"]["page_size"] == 20


def test_list_sermons_respects_page_size_query_param(client, db_session):
    _authed_client(client, db_session)

    response = client.get("/v1/sermons?page=2&page_size=5")

    body = response.json()
    assert response.status_code == 200
    assert body["data"]["page"] == 2
    assert body["data"]["page_size"] == 5


def test_get_sermon_detail_without_session_returns_401(client):
    import uuid

    response = client.get(f"/v1/sermons/{uuid.uuid4()}")

    assert response.status_code == 401


def test_get_sermon_detail_not_in_library_returns_404(client, db_session):
    _authed_client(client, db_session)
    import uuid

    response = client.get(f"/v1/sermons/{uuid.uuid4()}")

    body = response.json()
    assert response.status_code == 404
    assert body["success"] is False
    assert body["error"]["code"] == "sermon_not_found"


def test_get_completed_sermon_detail_returns_full_payload(client, db_session):
    from app.models.sermon import ProcessingStatus, Sermon
    from app.models.user_sermon import UserSermon

    user = _authed_client(client, db_session)
    sermon = Sermon(
        youtube_video_id="HTTP1",
        youtube_url="https://youtu.be/HTTP1",
        title="A Sermon",
        status=ProcessingStatus.COMPLETED,
    )
    db_session.add(sermon)
    db_session.flush()
    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    db_session.commit()

    response = client.get(f"/v1/sermons/{sermon.id}")

    body = response.json()
    assert response.status_code == 200
    assert body["data"]["title"] == "A Sermon"
    assert body["data"]["notes"] == []


def test_get_processing_sermon_returns_202_with_null_analysis(client, db_session):
    from app.models.sermon import ProcessingStatus, Sermon
    from app.models.user_sermon import UserSermon

    user = _authed_client(client, db_session)
    sermon = Sermon(
        youtube_video_id="HTTP2",
        youtube_url="https://youtu.be/HTTP2",
        status=ProcessingStatus.PROCESSING,
    )
    db_session.add(sermon)
    db_session.flush()
    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    db_session.commit()

    response = client.get(f"/v1/sermons/{sermon.id}")

    body = response.json()
    assert response.status_code == 202
    assert body["data"]["analysis"] is None


def test_delete_sermon_without_session_returns_401(client):
    import uuid

    response = client.delete(f"/v1/sermons/{uuid.uuid4()}")

    assert response.status_code == 401


def test_delete_sermon_not_in_library_returns_404(client, db_session):
    _authed_client(client, db_session)
    import uuid

    response = client.delete(f"/v1/sermons/{uuid.uuid4()}")

    body = response.json()
    assert response.status_code == 404
    assert body["error"]["code"] == "sermon_not_found"


def test_delete_sermon_removes_it_from_library(client, db_session):
    from app.models.sermon import ProcessingStatus, Sermon
    from app.models.user_sermon import UserSermon

    user = _authed_client(client, db_session)
    sermon = Sermon(
        youtube_video_id="HTTP3",
        youtube_url="https://youtu.be/HTTP3",
        status=ProcessingStatus.COMPLETED,
    )
    db_session.add(sermon)
    db_session.flush()
    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    db_session.commit()

    response = client.delete(f"/v1/sermons/{sermon.id}")

    assert response.status_code == 204
    assert db_session.query(UserSermon).filter_by(user_id=user.id, sermon_id=sermon.id).count() == 0
    # canonical Sermon row survives
    assert db_session.query(Sermon).filter_by(id=sermon.id).count() == 1


def test_retry_sermon_without_session_returns_401(client):
    import uuid

    response = client.post(f"/v1/sermons/{uuid.uuid4()}/retry")

    assert response.status_code == 401


def test_retry_sermon_not_in_library_returns_404(client, db_session):
    _authed_client(client, db_session)
    import uuid

    response = client.post(f"/v1/sermons/{uuid.uuid4()}/retry")

    body = response.json()
    assert response.status_code == 404
    assert body["error"]["code"] == "sermon_not_found"


def test_retry_non_failed_sermon_returns_409(client, db_session):
    from app.models.sermon import ProcessingStatus, Sermon
    from app.models.user_sermon import UserSermon

    user = _authed_client(client, db_session)
    sermon = Sermon(
        youtube_video_id="HTTP4",
        youtube_url="https://youtu.be/HTTP4",
        status=ProcessingStatus.COMPLETED,
    )
    db_session.add(sermon)
    db_session.flush()
    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    db_session.commit()

    response = client.post(f"/v1/sermons/{sermon.id}/retry")

    body = response.json()
    assert response.status_code == 409
    assert body["error"]["code"] == "sermon_not_retryable"


def test_retry_failed_sermon_resets_to_pending_and_reenqueues(client, db_session):
    from app.models.processing_job import ProcessingJob
    from app.models.sermon import ProcessingStatus, Sermon
    from app.models.user_sermon import UserSermon

    user = _authed_client(client, db_session)
    sermon = Sermon(
        youtube_video_id="HTTP5",
        youtube_url="https://youtu.be/HTTP5",
        status=ProcessingStatus.FAILED,
        failure_reason="No captions available",
    )
    db_session.add(sermon)
    db_session.flush()
    db_session.add(
        ProcessingJob(sermon_id=sermon.id, attempt_count=3, error_message="No captions available")
    )
    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    db_session.commit()

    with patch("app.services.sermon_service.process_sermon") as mock_task:
        response = client.post(f"/v1/sermons/{sermon.id}/retry")

    body = response.json()
    assert response.status_code == 200
    assert body["data"]["status"] == "pending"
    mock_task.delay.assert_called_once_with(str(sermon.id))

    db_session.refresh(sermon)
    assert sermon.status == ProcessingStatus.PENDING
    assert sermon.failure_reason is None
    job = db_session.query(ProcessingJob).filter_by(sermon_id=sermon.id).one()
    assert job.attempt_count == 0
    assert job.error_message is None
