import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session as DBSession

from app.models.session import Session as SessionModel
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

SESSION_TTL_DAYS = 7


class InvalidSessionError(Exception):
    """Raised when a session token doesn't match any known session."""


class SessionExpiredError(Exception):
    """Raised when a session token is valid but its expires_at has passed."""


class AuthService:
    """Business rules for authentication: Google sign-in (find-or-create),
    session issuance, session validation, and logout. Delegates data access
    to UserRepository/SessionRepository and owns the transaction boundary
    (commit) around each operation. Stays HTTP-agnostic - callers (deps.py)
    translate the exceptions here into the right HTTP response.
    """

    def __init__(self, db: DBSession, users: UserRepository, sessions: SessionRepository):
        self._db = db
        self._users = users
        self._sessions = sessions

    def get_or_create_user(self, google_userinfo: dict) -> User:
        """Find the user matching this Google account, or create one if
        this is their first sign-in. Keyed by google_id, since that's the
        stable identifier Google guarantees across sign-ins.
        """
        user = self._users.find_by_google_id(google_userinfo["sub"])
        if user is not None:
            return user

        user = User(
            google_id=google_userinfo["sub"],
            email=google_userinfo["email"],
            full_name=google_userinfo.get("name"),
            avatar_url=google_userinfo.get("picture"),
        )
        self._users.add(user)
        self._db.commit()
        self._db.refresh(user)
        return user

    def create_session(self, user: User) -> SessionModel:
        """Issue a new opaque session token for the given user."""
        session = SessionModel(
            token=secrets.token_urlsafe(32),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=SESSION_TTL_DAYS),
        )
        self._sessions.add(session)
        self._db.commit()
        return session

    def get_authenticated_user(self, session_token: str) -> User:
        """Resolve a session token to its User.

        Raises InvalidSessionError if the token doesn't match any session,
        SessionExpiredError if it matches one that's past expires_at.
        Deliberately distinct exceptions - the caller (deps.py) maps each to
        its own 401 error code.
        """
        session = self._sessions.find_by_token(session_token)
        if session is None:
            raise InvalidSessionError(f"No session found for token {session_token}")

        if session.expires_at < datetime.now(UTC):
            raise SessionExpiredError(f"Session {session_token} expired at {session.expires_at}")

        user = self._users.find_by_id(session.user_id)  # ty: ignore[invalid-argument-type]
        if user is None:
            raise InvalidSessionError(f"No user found for session {session_token}")
        return user

    def logout(self, session_token: str) -> None:
        """Delete the session for this token, if any. A no-op for an
        already-stale/nonexistent token - logout is idempotent.
        """
        self._sessions.delete_by_token(session_token)
        self._db.commit()
