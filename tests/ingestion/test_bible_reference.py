import pytest

from app.ingestion.bible_reference import BibleReferenceParseError, parse_reference


def test_parses_plain_reference():
    parsed = parse_reference("Romans 8:28")

    assert parsed.book == "Romans"
    assert parsed.chapter == 8
    assert parsed.verse_start == 28
    assert parsed.verse_end is None


def test_parses_numbered_book():
    parsed = parse_reference("1 Peter 3:8")

    assert parsed.book == "1 Peter"
    assert parsed.chapter == 3
    assert parsed.verse_start == 8


def test_parses_multi_word_book():
    parsed = parse_reference("Song of Solomon 2:1")

    assert parsed.book == "Song of Solomon"
    assert parsed.chapter == 2
    assert parsed.verse_start == 1


def test_parses_verse_range():
    parsed = parse_reference("Psalm 23:1-4")

    assert parsed.book == "Psalm"
    assert parsed.chapter == 23
    assert parsed.verse_start == 1
    assert parsed.verse_end == 4


def test_parses_chapter_only_reference_without_verses():
    parsed = parse_reference("Genesis 1")

    assert parsed.book == "Genesis"
    assert parsed.chapter == 1
    assert parsed.verse_start is None
    assert parsed.verse_end is None


def test_raises_typed_error_on_unparseable_text():
    with pytest.raises(BibleReferenceParseError):
        parse_reference("See the Bible")


def test_raises_typed_error_on_empty_string():
    with pytest.raises(BibleReferenceParseError):
        parse_reference("")
