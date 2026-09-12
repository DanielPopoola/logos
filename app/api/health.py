import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from app.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/healthz", include_in_schema=False)
def healthz(db: Annotated[DBSession, Depends(get_db)], response: Response):
    """Checked by the container platform to decide whether to route
    traffic to this instance or restart it - kept outside /v1 and
    unauthenticated, since a platform's health checker doesn't carry a
    session cookie.
    """
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database health check failed")
        response.status_code = 503
        return {"status": "error"}

    return {"status": "ok"}
