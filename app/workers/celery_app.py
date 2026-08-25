from celery import Celery
from celery.signals import celeryd_init, setup_logging
from sentry_sdk.integrations.celery import CeleryIntegration

from app.config import settings
from app.logging_config import configure_logging
from app.sentry_config import init_sentry

celery_app = Celery(
    "logos",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@setup_logging.connect
def _configure_worker_logging(**kwargs: object) -> None:
    """Replaces Celery's own logging setup with ours - connecting a
    receiver to this signal tells Celery to skip setup_logging_subsystem
    entirely, rather than racing it and losing.
    """
    configure_logging()


@celeryd_init.connect
def _init_worker_sentry(**kwargs: object) -> None:
    """celeryd_init is Sentry's documented signal for Celery: it fires
    before worker processes are spawned, so init happens early enough to
    catch startup errors too - initializing only inside a task or in
    tasks.py's module scope would be too late for some events.
    """
    init_sentry([CeleryIntegration()])
