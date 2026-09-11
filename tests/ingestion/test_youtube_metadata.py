from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.ingestion.youtube_metadata import (
    VideoMetadataNotFoundError,
    _parse_iso8601_duration,
    fetch_video_metadata,
)


def test_parse_iso8601_duration_hours_minutes_seconds():
    assert _parse_iso8601_duration("PT1H5M30S") == 1 * 3600 + 5 * 60 + 30


def test_parse_iso8601_duration_minutes_and_seconds_only():
    assert _parse_iso8601_duration("PT42M17S") == 42 * 60 + 17


def test_parse_iso8601_duration_minutes_only():
    assert _parse_iso8601_duration("PT38M") == 38 * 60


def test_parse_iso8601_duration_raises_on_unrecognized_format():
    with pytest.raises(ValueError, match="Unrecognized duration format"):
        _parse_iso8601_duration("not-a-duration")


def _mock_response(json_body: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_body
    response.raise_for_status.return_value = None
    return response


def test_fetch_video_metadata_returns_title_channel_and_duration():
    api_response = {
        "items": [
            {
                "snippet": {"title": "Walking by Faith", "channelTitle": "Grace City Church"},
                "contentDetails": {"duration": "PT48M0S"},
            }
        ]
    }
    with patch("httpx.get", return_value=_mock_response(api_response)):
        result = fetch_video_metadata("ABC123")

    assert result == {
        "title": "Walking by Faith",
        "channel_title": "Grace City Church",
        "duration_seconds": 48 * 60,
    }


def test_fetch_video_metadata_raises_not_found_when_no_items():
    with patch("httpx.get", return_value=_mock_response({"items": []})):
        with pytest.raises(VideoMetadataNotFoundError, match="ABC123"):
            fetch_video_metadata("ABC123")


def test_fetch_video_metadata_propagates_http_errors():
    """Quota/auth/server errors are surfaced, not swallowed - those are
    configuration problems the caller (and eventually the operator)
    should see, unlike a merely-missing video."""
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "quota exceeded", request=MagicMock(), response=MagicMock(status_code=403)
    )
    with patch("httpx.get", return_value=response):
        with pytest.raises(httpx.HTTPStatusError):
            fetch_video_metadata("ABC123")


@pytest.mark.slow
def test_fetch_video_metadata_returns_real_data_for_known_video():
    # "Me at the zoo" - the first video ever uploaded to YouTube, so its
    # metadata is stable and safe to assert on indefinitely.
    result = fetch_video_metadata("jNQXAC9IVRw")
    assert result["title"]
    assert result["channel_title"]
    assert result["duration_seconds"] > 0
