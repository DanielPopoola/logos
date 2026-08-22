import uuid

from pydantic import BaseModel

from app.models.sermon import ProcessingStatus


class SubmitSermonRequest(BaseModel):
    youtube_url: str


class SermonSubmissionOut(BaseModel):
    id: uuid.UUID
    status: ProcessingStatus
    youtube_url: str
