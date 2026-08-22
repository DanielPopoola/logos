import functools
import time

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

TRANSIENT_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError, APIStatusError)
NON_RETRYABLE_ERRORS = (
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
)


def _is_retryable(error: Exception) -> bool:
    """Auth/client errors are guaranteed to fail again identically, so retrying
    them just wastes time - only retry errors that might succeed on a later
    attempt (network blips, timeouts, rate limits, transient 5xx)."""
    if isinstance(error, NON_RETRYABLE_ERRORS):
        return False
    return isinstance(error, TRANSIENT_ERRORS)


def retry_on_transient_error(max_attempts: int = 3, initial_delay_seconds: float = 1):
    """Retry a function on transient LLM API errors (connection issues, timeouts,
    rate limits, 5xx) with exponential backoff. Non-transient errors (auth, bad
    request) propagate immediately without retrying.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay_seconds
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as error:
                    is_last_attempt = attempt == max_attempts
                    if not _is_retryable(error) or is_last_attempt:
                        raise
                    time.sleep(delay)
                    delay *= 2

        return wrapper

    return decorator
