import json
import logging
from datetime import UTC, datetime

from app.config import settings
from app.request_context import get_request_id

_RESERVED_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON, suitable for a container
    platform's stdout capture. Includes the current request_id (if any),
    so a request's log lines can be correlated with each other and with
    the request_id an error response returns to the client.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Anything passed via logger.info(..., extra={...}) rides along too,
        # so callers can attach structured context (e.g. sermon_id) without
        # this formatter needing to know about every possible field.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and key not in payload:
                payload[key] = value

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Set up JSON logging to stdout, called once at process startup by
    both the API and the Celery worker. Idempotent - safe to call more
    than once (e.g. in tests) without stacking duplicate handlers.
    """
    root = logging.getLogger()
    root.setLevel(settings.log_level)

    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
