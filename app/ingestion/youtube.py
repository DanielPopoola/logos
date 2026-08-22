from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi


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
    fetched = ytt.fetch(video_id)
    return [
        {"text": snippet.text, "start": snippet.start, "duration": snippet.duration}
        for snippet in fetched
    ]
