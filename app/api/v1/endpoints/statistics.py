from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, get_statistics_service
from app.models import User
from app.schemas import (
    CategoryStatisticsFilters,
    CategorySummaryResponse,
    StatisticsFilters,
    SummaryResponse,
)
from app.services import StatisticsService

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    filters: StatisticsFilters = Depends(),
    current_user: User = Depends(get_current_user),
    statistics_service: StatisticsService = Depends(get_statistics_service),
):
    return await statistics_service.get_summary(current_user.id, filters)


@router.get("/categories", response_model=CategorySummaryResponse)
async def get_categories(
    filters: CategoryStatisticsFilters = Depends(),
    current_user: User = Depends(get_current_user),
    statistics_service: StatisticsService = Depends(get_statistics_service),
):
    return await statistics_service.get_by_category(current_user.id, filters)
