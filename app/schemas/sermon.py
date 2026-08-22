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
