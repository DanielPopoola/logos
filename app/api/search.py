from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, get_search_service
from app.models.user import User
from app.schemas.response import APIResponse
from app.schemas.search import (
    SearchResponseOut,
    SearchResultOut,
)
from app.services.search_service import SearchService

router = APIRouter()


@router.get("", response_model=APIResponse[SearchResponseOut])
def search_sermons(
    user: Annotated[User, Depends(get_current_user)],
    search_service: Annotated[SearchService, Depends(get_search_service)],
    q: str = Query(..., min_length=1),
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
):
    response = search_service.semantic_search(user, q, limit)
    return APIResponse.ok(
        SearchResponseOut(
            results=[SearchResultOut.model_validate(r, from_attributes=True) for r in response.results],
            message=response.message,
        )
    )
