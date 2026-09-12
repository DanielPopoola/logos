import logging
import time
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)


def extract_video_id(url: str) -> str:
    """Extract the video ID from a YouTube URL."""
    parsed = urlparse(url)

    if parsed.netloc == "youtu.be":
        video_id = parsed.path.lstrip("/")
        if video_id:
            return video_id
        raise ValueError(f"Could not extract video ID from URL: {url}")

    video_id = parse_qs(parsed.query).get("v")
    if video_id:
        return video_id[0]

    raise ValueError(f"Could not extract video ID from URL: {url}")


def get_transcript(url: str) -> list[dict]:
    """Fetch the transcript as a list of {text, start, duration} snippets."""
    video_id = extract_video_id(url)
    ytt = YouTubeTranscriptApi()
    started_at = time.perf_counter()
    try:
        fetched = ytt.fetch(video_id)
    except Exception:
        logger.warning(
            "External API call failed",
            exc_info=True,
            extra={
                "provider": "youtube",
                "operation": "fetch_transcript",
                "video_id": video_id,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        raise
    snippets = [
        {"text": snippet.text, "start": snippet.start, "duration": snippet.duration}
        for snippet in fetched
    ]
    logger.info(
        "External API call completed",
        extra={
            "provider": "youtube",
            "operation": "fetch_transcript",
            "video_id": video_id,
            "snippet_count": len(snippets),
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
        },
    )
    return snippets
