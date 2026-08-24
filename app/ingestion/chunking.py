DEFAULT_MAX_CHARS = 1500


def _build_chunk(texts: list[str], start: float, end: float) -> dict:
    return {
        "text": " ".join(texts).strip(),
        "start_timestamp": start,
        "end_timestamp": end,
    }


def chunk_transcript(snippets: list[dict], max_chars: int = DEFAULT_MAX_CHARS) -> list[dict]:
    """Group transcript snippets into chunks, each roughly max_chars long,
    carrying the start/end timestamp of the snippets they contain."""
    if not snippets:
        return []

    chunks = []
    current_texts: list[str] = []
    current_start = snippets[0]["start"]
    current_length = 0
    last_end = current_start

    for snippet in snippets:
        text = snippet["text"]
        snippet_end = snippet["start"] + snippet["duration"]

        if current_length + len(text) > max_chars and current_texts:
            chunks.append(_build_chunk(current_texts, current_start, last_end))
            current_texts = []
            current_start = snippet["start"]
            current_length = 0

        current_texts.append(text)
        current_length += len(text) + 1
        last_end = snippet_end

    if current_texts:
        chunks.append(_build_chunk(current_texts, current_start, last_end))

    return chunks
