import logging

from app.workers.celery_app import _log_task_failure


class _FakeSender:
    name = "app.workers.tasks.process_sermon"


def test_logs_task_failure_with_exception_info(caplog):
    try:
        raise ValueError("1 Peter 3 parsing exploded")
    except ValueError as exc:
        with caplog.at_level(logging.ERROR):
            _log_task_failure(
                sender=_FakeSender(),
                task_id="abc-123",
                exception=exc,
                args=("sermon-id-1",),
                kwargs={},
                traceback=exc.__traceback__,
                einfo=None,
            )

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) == 1
    assert error_records[0].exc_info is not None
    assert error_records[0].exc_info[0] is ValueError
    assert "process_sermon" in error_records[0].message
    assert error_records[0].task_id == "abc-123"


def test_logs_task_failure_even_without_a_sender():
    # sender can be None in edge cases (e.g. a misconfigured task) - the
    # handler must not itself crash while trying to log a crash.
    _log_task_failure(
        sender=None,
        task_id="abc-123",
        exception=ValueError("boom"),
        args=(),
        kwargs={},
        traceback=None,
        einfo=None,
    )
