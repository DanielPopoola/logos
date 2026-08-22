import pytest

from app.ingestion.youtube import extract_video_id, get_transcript


def test_extract_video_id_from_standard_watch_url():
    url = "https://www.youtube.com/watch?v=ABC123xyz45"
    assert extract_video_id(url) == "ABC123xyz45"


def test_extract_video_id_from_short_link():
    url = "https://youtu.be/ABC123xyz45"
    assert extract_video_id(url) == "ABC123xyz45"


def test_extract_video_id_raises_clear_error_on_unparseable_url():
    with pytest.raises(ValueError, match="Could not extract video ID"):
        extract_video_id("https://example.com/not-a-youtube-link")


@pytest.mark.slow
def test_get_transcript_returns_snippets_with_timestamps_for_real_video():
    snippets = get_transcript("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    assert isinstance(snippets, list)
    assert len(snippets) > 0
    first = snippets[0]
    assert isinstance(first["text"], str) and len(first["text"]) > 0
    assert isinstance(first["start"], float)
    assert isinstance(first["duration"], float)
