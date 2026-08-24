"""Guards against silent field drift between the service-layer dataclasses
(app/services/sermon_service.py) and their paired Pydantic response schemas
(app/schemas/sermon.py). The two exist separately on purpose - the service
stays framework-agnostic, the schema is the API's validation/serialization
boundary - but that means an added/removed/renamed field on one side has to
be mirrored by hand on the other, and model_validate(..., from_attributes=True)
would otherwise drop a mismatched field silently instead of raising. These
tests make that mismatch a loud, immediate test failure.

Not every dataclass has a schema pair, and not every schema validates a
dataclass - SermonSubmissionOut and NoteCreateOut/NoteUpdateOut validate
against ORM models directly (Sermon, UserNote) and intentionally expose a
narrower field set. Those aren't checked here; narrowing is the intended
behavior for them, not drift.
"""

import dataclasses

from app.schemas.sermon import (
    LibraryItemOut,
    LibraryPageOut,
    NoteOutSchema,
    SermonAnalysisOutSchema,
    SermonDetailOut,
)
from app.services.sermon_service import (
    LibraryItem,
    LibraryPage,
    NoteOut,
    SermonAnalysisOut,
    SermonDetail,
)


def _dataclass_field_names(cls) -> set[str]:
    return {f.name for f in dataclasses.fields(cls)}


def _schema_field_names(cls) -> set[str]:
    return set(cls.model_fields.keys())


def test_library_item_matches_library_item_out():
    assert _dataclass_field_names(LibraryItem) == _schema_field_names(LibraryItemOut)


def test_library_page_matches_library_page_out():
    assert _dataclass_field_names(LibraryPage) == _schema_field_names(LibraryPageOut)


def test_sermon_analysis_out_matches_schema():
    assert _dataclass_field_names(SermonAnalysisOut) == _schema_field_names(SermonAnalysisOutSchema)


def test_note_out_matches_schema():
    assert _dataclass_field_names(NoteOut) == _schema_field_names(NoteOutSchema)


def test_sermon_detail_matches_sermon_detail_out():
    assert _dataclass_field_names(SermonDetail) == _schema_field_names(SermonDetailOut)
