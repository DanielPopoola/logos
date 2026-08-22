import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session as DBSession

from app.models.session import Session as SessionModel
from app.models.user import User

SESSION_TTL_DAYS = 7


def get_or_create_user(db: DBSession, google_userinfo: dict) -> User:
    """Find the user matching this Google account, or create one if this is
    their first sign-in. Keyed by google_id, since that's the stable
    identifier Google guarantees across sign-ins.
    """
    user = db.query(User).filter_by(google_id=google_userinfo["sub"]).first()
    if user is not None:
        return user

    user = User(
        google_id=google_userinfo["sub"],
        email=google_userinfo["email"],
        full_name=google_userinfo.get("name"),
        avatar_url=google_userinfo.get("picture"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_session(db: DBSession, user: User) -> SessionModel:
    """Issue a new opaque session token for the given user."""
    session = SessionModel(
        token=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=SESSION_TTL_DAYS),
    )
    db.add(session)
    db.commit()
    return session
