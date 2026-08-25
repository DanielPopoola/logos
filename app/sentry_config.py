import sentry_sdk
from sentry_sdk.integrations import Integration

from app.config import settings


def init_sentry(integrations: list[Integration]) -> None:
    """Initializes Sentry error reporting for the current process.

    A no-op when sentry_dsn is unset - local dev and CI never need a
    Sentry account configured. Call once per process: main.py for the API,
    celery_app.py for the worker - they're separate processes and each
    needs its own init with its own integrations.
    """
    if settings.sentry_dsn is None:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        integrations=integrations,
    )
