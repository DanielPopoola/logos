import uuid

from pydantic import BaseModel


class SearchResultOut(BaseModel):
    sermon_id: uuid.UUID
    sermon_title: str | None
    speaker: str | None
    matched_excerpt: str
    timestamp_seconds: int | None
    relevance_score: float


class SearchResponseOut(BaseModel):
    results: list[SearchResultOut]
