import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session as DBSession

from app.config import settings
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
            logger.info("Authenticated user found", extra={"user_id": str(user.id)})
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
        logger.info("Authenticated user created", extra={"user_id": str(user.id)})
        return user

    def create_session(self, user: User) -> str:
        raw_token = secrets.token_urlsafe(32)
        session = SessionModel(
            token=self._hash_session_token(raw_token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=SESSION_TTL_DAYS),
        )
        self._sessions.add(session)
        self._db.commit()
        logger.info("Authentication session created", extra={"user_id": str(user.id)})
        return raw_token

    @staticmethod
    def _hash_session_token(token: str) -> str:
        secret = settings.session_token_hash_secret or settings.google_client_secret
        return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()

    def get_authenticated_user(self, session_token: str) -> User:
        """Resolve a session token to its User.

        Raises InvalidSessionError if the token doesn't match any session,
        SessionExpiredError if it matches one that's past expires_at.
        Deliberately distinct exceptions - the caller (deps.py) maps each to
        its own 401 error code.
        """
        session = self._sessions.find_by_token(self._hash_session_token(session_token))
        if session is None:
            logger.warning("Authentication session rejected", extra={"auth_reason": "invalid"})
            raise InvalidSessionError("No session found for supplied session token")

        if session.expires_at < datetime.now(UTC):
            logger.warning(
                "Authentication session rejected",
                extra={"auth_reason": "expired", "user_id": str(session.user_id)},
            )
            raise SessionExpiredError("Supplied session token has expired")

        user = self._users.find_by_id(session.user_id)  # ty: ignore[invalid-argument-type]
        if user is None:
            logger.warning(
                "Authentication session rejected",
                extra={"auth_reason": "user_not_found", "user_id": str(session.user_id)},
            )
            raise InvalidSessionError("No user found for supplied session token")
        return user

    def logout(self, session_token: str) -> None:
        """Delete the session for this token, if any. A no-op for an
        already-stale/nonexistent token - logout is idempotent.
        """
        self._sessions.delete_by_token(self._hash_session_token(session_token))
        self._db.commit()
