import re

import httpx

from app.config import settings

YOUTUBE_DATA_API_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

# Matches ISO 8601 durations as returned by contentDetails.duration, e.g.
# "PT42M17S", "PT1H5M", "PT38M". Named groups default to None when absent.
_ISO_8601_DURATION_PATTERN = re.compile(
    r"PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)


class VideoMetadataNotFoundError(Exception):
    """Raised when the YouTube Data API has no video for the given ID
    (private, deleted, or invalid ID)."""


def _parse_iso8601_duration(duration: str) -> int:
    """Converts an ISO 8601 duration string (e.g. "PT42M17S") to whole seconds."""
    match = _ISO_8601_DURATION_PATTERN.fullmatch(duration)
    if not match:
        raise ValueError(f"Unrecognized duration format: {duration!r}")

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return hours * 3600 + minutes * 60 + seconds


def fetch_video_metadata(video_id: str) -> dict:
    """Fetches title, channel name, and duration for a YouTube video.

    Uses the YouTube Data API v3 (a different Google service from
    youtube_transcript_api, which only provides captions and has no
    metadata capability at all). Returns a dict with keys: title,
    channel_title, duration_seconds.

    Raises VideoMetadataNotFoundError if the video doesn't exist or isn't
    public. Raises httpx.HTTPStatusError for other API errors (bad key,
    quota exceeded, etc.) - deliberately not swallowed, since those are
    configuration problems the caller should surface, not silently
    tolerate the way a missing title might be.
    """
    response = httpx.get(
        YOUTUBE_DATA_API_VIDEOS_URL,
        params={
            "part": "snippet,contentDetails",
            "id": video_id,
            "key": settings.youtube_data_api_key,
        },
    )
    response.raise_for_status()
    payload = response.json()

    items = payload.get("items", [])
    if not items:
        raise VideoMetadataNotFoundError(
            f"No video found for ID {video_id!r} (private, deleted, or invalid)"
        )

    video = items[0]
    return {
        "title": video["snippet"]["title"],
        "channel_title": video["snippet"]["channelTitle"],
        "duration_seconds": _parse_iso8601_duration(video["contentDetails"]["duration"]),
    }
