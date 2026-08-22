from datetime import UTC, datetime, timedelta

from app.models.session import Session as SessionModel
from app.models.user import User


def test_deleting_user_cascades_to_sessions(db_session):
    user = User(google_id="abc123", email="a@example.com", full_name="A")
    db_session.add(user)
    db_session.commit()

    session = SessionModel(
        token="opaque-token-123",
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add(session)
    db_session.commit()

    db_session.delete(user)
    db_session.commit()

    remaining = db_session.query(SessionModel).filter_by(token="opaque-token-123").first()
    assert remaining is None
