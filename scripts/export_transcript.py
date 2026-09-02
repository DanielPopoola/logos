# scripts/export_transcript.py
"""
Export a sermon's stored transcript to a neatly formatted .txt file.

Reads straight from the sermons table (app.database.get_db_session) using
the app's own DATABASE_URL config - no separate connection string to keep
in sync.

Usage:
    uv run python scripts/export_transcript.py <sermon_id> [output_path]

If output_path is omitted, saves to transcripts/<sermon_id>.txt
(directory created if it doesn't exist).
"""

import sys
import textwrap
import uuid
from pathlib import Path

from app.database import get_db_session

# Every model module must be imported before any query runs, so SQLAlchemy
# can resolve string-based relationship() references (e.g. Sermon's
# secondary="sermon_themes") across the full mapper registry. Mirrors the
# same requirement in alembic/env.py.
from app.models import (  # noqa: F401
    processing_job,
    sermon,
    sermon_analysis,
    sermon_chunk,
    session,
    taxonomy,
    user,
    user_note,
    user_sermon,
)
from app.models.sermon import Sermon

WRAP_WIDTH = 100


def export_transcript(sermon_id: uuid.UUID, output_path: Path) -> None:
    db = get_db_session()
    try:
        sermon = db.get(Sermon, sermon_id)
    finally:
        db.close()

    if sermon is None:
        print(f"No sermon found with id {sermon_id}")
        sys.exit(1)

    if not sermon.transcript:
        print(f"Sermon {sermon_id} has no transcript stored (status={sermon.status}).")
        if sermon.failure_reason:
            print(f"Failure reason: {sermon.failure_reason}")
        sys.exit(1)

    header_lines = [
        f"Title:      {sermon.title or '(untitled)'}",
        f"Speaker:    {sermon.speaker or '(unknown)'}",
        f"Sermon ID:  {sermon.id}",
        f"YouTube:    {sermon.youtube_url}",
        f"Status:     {sermon.status}",
    ]
    header = "\n".join(header_lines)
    divider = "=" * WRAP_WIDTH

    body = textwrap.fill(sermon.transcript, width=WRAP_WIDTH)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{header}\n{divider}\n\n{body}\n", encoding="utf-8")

    print(f"Saved transcript ({len(sermon.transcript)} chars) to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("Usage: uv run python scripts/export_transcript.py <sermon_id> [output_path]")
        sys.exit(1)

    try:
        parsed_id = uuid.UUID(sys.argv[1])
    except ValueError:
        print(f"'{sys.argv[1]}' is not a valid UUID")
        sys.exit(1)

    out_path = Path(sys.argv[2]) if len(sys.argv) == 3 else Path(f"transcripts/{parsed_id}.txt")
    export_transcript(parsed_id, out_path)
