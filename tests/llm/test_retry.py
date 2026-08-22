from unittest.mock import MagicMock, patch

import pytest
from openai import APIConnectionError, AuthenticationError

from app.llm.retry import retry_on_transient_error


def _connection_error():
    return APIConnectionError(request=MagicMock())


def test_retries_transient_error_and_returns_success_value():
    call_count = 0

    @retry_on_transient_error(max_attempts=3, initial_delay_seconds=0)
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise _connection_error()
        return "success"

    with patch("app.llm.retry.time.sleep"):
        result = flaky()

    assert result == "success"
    assert call_count == 3


def test_raises_after_exhausting_max_attempts():
    call_count = 0

    @retry_on_transient_error(max_attempts=3, initial_delay_seconds=0)
    def always_fails():
        nonlocal call_count
        call_count += 1
        raise _connection_error()

    with patch("app.llm.retry.time.sleep"):
        with pytest.raises(APIConnectionError):
            always_fails()

    assert call_count == 3


def test_does_not_retry_non_transient_error():
    call_count = 0

    @retry_on_transient_error(max_attempts=3, initial_delay_seconds=0)
    def bad_auth():
        nonlocal call_count
        call_count += 1
        raise AuthenticationError(message="bad key", response=MagicMock(), body=None)

    with pytest.raises(AuthenticationError):
        bad_auth()

    assert call_count == 1


def test_waits_with_exponential_backoff_between_attempts():
    call_count = 0

    @retry_on_transient_error(max_attempts=3, initial_delay_seconds=1)
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise _connection_error()
        return "success"

    with patch("app.llm.retry.time.sleep") as mock_sleep:
        flaky()

    assert mock_sleep.call_args_list == [((1,),), ((2,),)]
