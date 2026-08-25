import uuid
from contextvars import ContextVar

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str:
    """Return the current request's ID, generating one if none is set.

    Falls back to a fresh UUID outside a request context (e.g. a script or
    test calling code directly) so callers never need a None check.
    """
    return _request_id_var.get() or str(uuid.uuid4())


def set_request_id(value: str) -> None:
    _request_id_var.set(value)
