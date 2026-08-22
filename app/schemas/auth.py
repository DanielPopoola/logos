import uuid

from pydantic import BaseModel


class GoogleAuthRequest(BaseModel):
    id_token: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    avatar_url: str | None


class GoogleAuthResponse(BaseModel):
    user: UserOut
    session_token: str
