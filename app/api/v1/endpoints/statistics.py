from fastapi import APIRouter, Depends

from app.api.dependencies import get_statistics_service, get_current_user
from app.services import StatisticsService
from app.schemas import SummaryResponse, StatisticsFilters, CategoryStatisticsFilters, CategorySummaryResponse
from app.models import User

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get(
    "/summary",
    response_model=SummaryResponse
)
async def get_summary(
        filters: StatisticsFilters = Depends(),
        current_user: User = Depends(get_current_user),
        statistics_service: StatisticsService = Depends(get_statistics_service)
):
    return await statistics_service.get_summary(current_user.id, filters)


@router.get("/categories", response_model=CategorySummaryResponse)
async def get_categories(
        filters: CategoryStatisticsFilters = Depends(),
        current_user: User = Depends(get_current_user),
        statistics_service: StatisticsService = Depends(get_statistics_service),
):
    return await statistics_service.get_by_category(current_user.id, filters)
