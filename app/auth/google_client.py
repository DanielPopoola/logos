import logging
import time

import httpx

from app.config import settings

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
logger = logging.getLogger(__name__)


def exchange_code_for_tokens(code: str) -> dict:
    """Exchange an OAuth authorization code for Google access/ID tokens."""
    started_at = time.perf_counter()
    try:
        response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        logger.info(
            "External API call completed",
            extra={
                "provider": "google",
                "operation": "exchange_code_for_tokens",
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return response.json()
    except Exception:
        logger.warning(
            "External API call failed",
            exc_info=True,
            extra={
                "provider": "google",
                "operation": "exchange_code_for_tokens",
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        raise


def fetch_google_userinfo(access_token: str) -> dict:
    """Fetch the Google account's profile (sub, email, name, picture) for
    the given access token. Shape matches what auth_service.get_or_create_user
    expects.
    """
    started_at = time.perf_counter()
    try:
        response = httpx.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        logger.info(
            "External API call completed",
            extra={
                "provider": "google",
                "operation": "fetch_userinfo",
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return response.json()
    except Exception:
        logger.warning(
            "External API call failed",
            exc_info=True,
            extra={
                "provider": "google",
                "operation": "fetch_userinfo",
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        raise
