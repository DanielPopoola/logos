import logging

from celery import Celery
from celery.signals import celeryd_init, setup_logging, task_failure
from sentry_sdk.integrations.celery import CeleryIntegration

from app.config import settings
from app.logging_config import configure_logging
from app.sentry_config import init_sentry

logger = logging.getLogger(__name__)

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
    # --- Graceful shutdown (container-platform SIGTERM/SIGKILL contract) ---
    # Only one task fetched at a time per worker process - keeps shutdown
    # coordination simple (never more than one in-flight task to wait for
    # or lose) and matches process_sermon's shape: a few minutes long,
    # calling external APIs (YouTube, Gemini), not a high-throughput
    # short-task workload where prefetching would matter for throughput.
    worker_prefetch_multiplier=1,
    # The task is acknowledged only after it completes, not the moment
    # it's received. Combined with task_reject_on_worker_lost, a task that
    # was mid-flight when the worker was hard-killed (SIGKILL after the
    # platform's grace period expires) is requeued rather than silently
    # lost. This is safe specifically because IngestionService.run is
    # already idempotent (see Epic 3.6/has_analysis/has_chunks) - a retried
    # sermon doesn't produce duplicate rows.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Celery 5.5+'s bounded warm shutdown: on SIGTERM, the worker stops
    # accepting new tasks and gets this many seconds to let the current
    # task finish before a cold shutdown is forced. Set this comfortably
    # above process_sermon's worst-case duration, and make sure the
    # container platform's own termination grace period (e.g. Kubernetes'
    # terminationGracePeriodSeconds, or the equivalent on Fly/Render) is
    # configured to exceed this value too - otherwise the platform's
    # SIGKILL arrives before this timeout even elapses.
    worker_soft_shutdown_timeout=180,
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


@task_failure.connect
def _log_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    einfo=None,
    **extra: object,
) -> None:
    """Fires for any exception a task doesn't catch itself - this is the
    Celery-side counterpart to UnhandledExceptionMiddleware: a structured,
    correlatable log line instead of a traceback that only ever reached the
    worker's console (which is exactly what happened with the Bible
    reference parsing bug before it was fixed at the source).

    task_failure does not fire for a task killed by SIGKILL/OOM
    (WorkerLostError) - that's a different failure mode, addressed by
    graceful shutdown configuration, not this signal.

    Sentry's CeleryIntegration already reports failures to Sentry on its
    own; this handler is only responsible for the structured log line, not
    duplicate error reporting.
    """
    task_name = sender.name if sender is not None else "unknown_task"
    logger.error(
        "Task failure: %s[%s]: %s",
        task_name,
        task_id,
        exception,
        exc_info=(type(exception), exception, traceback) if exception else None,
        extra={"task_name": task_name, "task_id": task_id, "task_args": args},
    )
