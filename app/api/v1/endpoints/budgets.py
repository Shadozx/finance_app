from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_budget_service, get_current_user
from app.models import User
from app.schemas import (
    BudgetCreate,
    BudgetFilters,
    BudgetResponse,
    BudgetStatusResponse,
    BudgetUpdate,
    Page,
)
from app.services import BudgetService

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BudgetResponse)
async def create_budget(
    data: BudgetCreate,
    current_user: User = Depends(get_current_user),
    budget_service: BudgetService = Depends(get_budget_service),
):
    return await budget_service.create_budget(data, current_user.id)


@router.get("", response_model=Page[BudgetStatusResponse])
async def get_user_budgets(
    filters: BudgetFilters = Depends(),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    budget_service: BudgetService = Depends(get_budget_service),
):
    return await budget_service.get_user_budgets(current_user.id, filters, limit, offset)


@router.get("/{budget_id}", response_model=BudgetResponse)
async def get_budget(
    budget_id: int,
    current_user: User = Depends(get_current_user),
    budget_service: BudgetService = Depends(get_budget_service),
):
    return await budget_service.get_budget(budget_id, current_user.id)


@router.get("/{budget_id}/status", response_model=BudgetStatusResponse)
async def get_budget_status(
    budget_id: int,
    current_user: User = Depends(get_current_user),
    budget_service: BudgetService = Depends(get_budget_service),
):
    return await budget_service.get_budget_status(budget_id, current_user.id)


@router.put("/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: int,
    data: BudgetUpdate,
    current_user: User = Depends(get_current_user),
    budget_service: BudgetService = Depends(get_budget_service),
):
    return await budget_service.update_budget(budget_id, data, current_user.id)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    budget_id: int,
    current_user: User = Depends(get_current_user),
    budget_service: BudgetService = Depends(get_budget_service),
):
    await budget_service.delete_budget(budget_id, current_user.id)
