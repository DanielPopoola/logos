# scripts/verify_video_metadata.py
"""
Manual smoke test for the YouTube video metadata module.

Tests:
1. ISO 8601 duration parsing.
2. Fetching real metadata from the YouTube Data API.

Usage:
    uv run python scripts/verify_video_metadata.py "VIDEO_ID"

Example:
    uv run python scripts/verify_video_metadata.py dQw4w9WgXcQ
"""

import sys

from app.ingestion.youtube_metadata import (
    VideoMetadataNotFoundError,
    _parse_iso8601_duration,
    fetch_video_metadata,
)


def test_duration_parser():
    print("--- Testing ISO 8601 duration parser ---")

    test_cases = {
        "PT42M17S": 2537,
        "PT1H5M": 3900,
        "PT38M": 2280,
        "PT1H": 3600,
        "PT45S": 45,
        "PT2H30M15S": 9015,
        "PT0S": 0,
    }

    for duration, expected in test_cases.items():
        actual = _parse_iso8601_duration(duration)

        if actual != expected:
            raise AssertionError(f"{duration}: expected {expected}, got {actual}")

        print(f"  ✓ {duration} -> {actual}s")

    print("Duration parser passed.\n")


def test_video_metadata(video_id: str):
    print(f"--- Fetching metadata for video {video_id} ---")

    try:
        metadata = fetch_video_metadata(video_id)
    except VideoMetadataNotFoundError as exc:
        print(f"Video metadata not found: {exc}")
        return

    print("\nMetadata:")
    print(f"  Title:           {metadata['title']}")
    print(f"  Channel:         {metadata['channel_title']}")
    print(f"  Duration:        {metadata['duration_seconds']} seconds")

    duration = metadata["duration_seconds"]
    hours, remainder = divmod(duration, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        formatted_duration = f"{hours}h {minutes}m {seconds}s"
    elif minutes:
        formatted_duration = f"{minutes}m {seconds}s"
    else:
        formatted_duration = f"{seconds}s"

    print(f"  Formatted:       {formatted_duration}")

    print("\n✓ YouTube metadata fetch passed.")


def main(video_id: str):
    test_duration_parser()
    test_video_metadata(video_id)

    print("\n--- All smoke tests completed. ---")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run python scripts/verify_video_metadata.py <youtube_video_id>")
        sys.exit(1)

    main(sys.argv[1])
