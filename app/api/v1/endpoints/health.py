import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_session

logger = structlog.get_logger()

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health():
    return {"status": "ok"}


@router.get(
    "/ready",
    responses={
        200: {"description": "Service is ready"},
        503: {"description": "Service is not ready"},
    },
)
async def ready(
    session: AsyncSession = Depends(get_session),
):
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        logger.error("db_health_check_failed", exc_info=True)

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable"
        )
