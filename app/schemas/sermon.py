import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.sermon import ProcessingStatus


class SubmitSermonRequest(BaseModel):
    youtube_url: str


class SermonSubmissionOut(BaseModel):
    id: uuid.UUID
    status: ProcessingStatus
    youtube_url: str


class LibraryItemOut(BaseModel):
    id: uuid.UUID
    title: str | None
    speaker: str | None
    status: ProcessingStatus
    duration_seconds: int | None
    summary_excerpt: str | None
    themes: list[str]
    saved_at: datetime


class LibraryPageOut(BaseModel):
    items: list[LibraryItemOut]
    page: int
    page_size: int
    total: int


class SermonAnalysisOutSchema(BaseModel):
    summary: str | None
    key_teachings: list[str]
    action_points: list[str]
    reflection_questions: list[str]


class NoteOutSchema(BaseModel):
    id: uuid.UUID
    content: str
    created_at: datetime


class SermonDetailOut(BaseModel):
    id: uuid.UUID
    youtube_url: str
    title: str | None
    speaker: str | None
    duration_seconds: int | None
    status: ProcessingStatus
    failure_reason: str | None
    saved_at: datetime
    analysis: SermonAnalysisOutSchema | None
    themes: list[str]
    bible_references: list[str]
    notes: list[NoteOutSchema]


class CreateNoteRequest(BaseModel):
    content: str


class UpdateNoteRequest(BaseModel):
    content: str


class NoteCreateOut(BaseModel):
    id: uuid.UUID
    content: str
    created_at: datetime


class NoteUpdateOut(BaseModel):
    id: uuid.UUID
    content: str
    updated_at: datetime
