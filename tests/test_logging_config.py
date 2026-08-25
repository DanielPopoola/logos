import json
import logging

from app.logging_config import JSONFormatter
from app.request_context import set_request_id


def _make_record(message: str, level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord(
        name="test.logger",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_formats_record_as_valid_json_with_expected_fields():
    formatter = JSONFormatter()
    record = _make_record("hello world")

    output = json.loads(formatter.format(record))

    assert output["message"] == "hello world"
    assert output["level"] == "INFO"
    assert output["logger"] == "test.logger"
    assert "timestamp" in output


def test_includes_current_request_id_when_set():
    formatter = JSONFormatter()
    set_request_id("req-abc-123")
    record = _make_record("inside a request")

    output = json.loads(formatter.format(record))

    assert output["request_id"] == "req-abc-123"


def test_includes_exception_info_when_present():
    formatter = JSONFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _make_record("something broke")
        record.exc_info = sys.exc_info()

    output = json.loads(formatter.format(record))

    assert "ValueError" in output["exception"]
    assert "boom" in output["exception"]
