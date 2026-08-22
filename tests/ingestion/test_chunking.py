from app.ingestion.chunking import chunk_transcript


def test_short_transcript_produces_exactly_one_chunk():
    snippets = [
        {"text": "In the beginning", "start": 0.0, "duration": 2.0},
        {"text": "God created the heavens and the earth.", "start": 2.0, "duration": 3.0},
    ]

    chunks = chunk_transcript(snippets, max_chars=500)

    assert len(chunks) == 1
    assert chunks[0]["text"] == "In the beginning God created the heavens and the earth."


def test_long_transcript_produces_multiple_chunks_within_target_size():
    snippets = [{"text": "word " * 20, "start": float(i * 5), "duration": 5.0} for i in range(20)]

    chunks = chunk_transcript(snippets, max_chars=200)

    assert len(chunks) > 1
    for chunk in chunks:
        assert (
            len(chunk["text"]) <= 200 + 25
        )  # small slack: a chunk stops after the snippet that crosses the limit


def test_chunk_boundaries_carry_correct_timestamps():
    snippets = [{"text": "word " * 20, "start": float(i * 5), "duration": 5.0} for i in range(20)]

    chunks = chunk_transcript(snippets, max_chars=200)

    for i, chunk in enumerate(chunks):
        assert chunk["start_timestamp"] >= 0
        assert chunk["end_timestamp"] > chunk["start_timestamp"]
        if i > 0:
            # chunks should be in chronological order, non-overlapping
            assert chunk["start_timestamp"] >= chunks[i - 1]["end_timestamp"]
