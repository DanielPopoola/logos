from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas.response import APIResponse, ErrorDetail


class AppException(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    import uuid

    body = APIResponse.fail(
        ErrorDetail(code=exc.code, message=exc.message, request_id=str(uuid.uuid4()))
    )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())
