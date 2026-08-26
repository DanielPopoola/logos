import re
from dataclasses import dataclass

_REFERENCE_PATTERN = re.compile(
    r"^(?P<book>\d?\s?[A-Za-z][A-Za-z\s]*?)\s+(?P<chapter>\d+)"
    r"(?::(?P<verse_start>\d+)(?:-(?P<verse_end>\d+))?)?$"
)


class BibleReferenceParseError(Exception):
    """Raised when a display_text string doesn't match the expected Bible
    reference shape - mirrors ingestion/analysis.py's pattern of raising a
    typed error on malformed LLM output rather than crashing or silently
    producing garbage.
    """


@dataclass
class ParsedReference:
    book: str
    chapter: int
    verse_start: int | None
    verse_end: int | None


def parse_reference(display_text: str) -> ParsedReference:
    """Parses a Bible reference string like "1 Peter 3:8" or "Song of
    Solomon 2:1-4" into its book, chapter, and optional verse range.

    Handles numbered books ("1 Peter", "2 Corinthians", "3 John") and
    multi-word books ("Song of Solomon") - a naive split on the first space
    breaks on both of these, since "1" or "Song" would be mistaken for the
    whole book name.
    """
    match = _REFERENCE_PATTERN.match(display_text.strip())
    if match is None:
        raise BibleReferenceParseError(f"Could not parse Bible reference: {display_text!r}")

    verse_start = match.group("verse_start")
    verse_end = match.group("verse_end")
    return ParsedReference(
        book=match.group("book").strip(),
        chapter=int(match.group("chapter")),
        verse_start=int(verse_start) if verse_start is not None else None,
        verse_end=int(verse_end) if verse_end is not None else None,
    )
