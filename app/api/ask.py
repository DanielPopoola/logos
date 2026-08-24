from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_search_service
from app.models.user import User
from app.schemas.response import APIResponse
from app.schemas.search import AskRequest, AskResponseOut, SourceOut
from app.services.search_service import SearchService

router = APIRouter()


@router.post("", response_model=APIResponse[AskResponseOut])
def ask_question(
    body: AskRequest,
    user: Annotated[User, Depends(get_current_user)],
    search_service: Annotated[SearchService, Depends(get_search_service)],
):
    result = search_service.answer_question(user, body.question)
    return APIResponse.ok(
        AskResponseOut(
            answer=result.answer,
            sources=[SourceOut.model_validate(s, from_attributes=True) for s in result.sources],
        )
    )
