from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_current_user
from app.database import get_db
from app.errors import AppException
from app.models.user import User
from app.schemas.response import APIResponse
from app.schemas.sermon import SermonSubmissionOut, SubmitSermonRequest
from app.services.sermon_service import submit_sermon

router = APIRouter()


@router.post("", response_model=APIResponse[SermonSubmissionOut])
def create_sermon(
    body: SubmitSermonRequest,
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[DBSession, Depends(get_db)],
):
    try:
        result = submit_sermon(db, user, body.youtube_url)
    except ValueError as e:
        raise AppException(status_code=400, code="invalid_youtube_url", message=str(e)) from e

    response.status_code = result.status_code
    return APIResponse.ok(SermonSubmissionOut.model_validate(result.sermon, from_attributes=True))
