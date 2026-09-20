from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_category_service, get_current_user
from app.models import TransactionType, User
from app.schemas import CategoryCreate, CategoryResponse, CategoryStatus, CategoryUpdate, Page
from app.services import CategoryService

router = APIRouter(prefix="/categories", tags=["categories"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CategoryResponse)
async def create_category(
    data: CategoryCreate,
    current_user: User = Depends(get_current_user),
    category_service: CategoryService = Depends(get_category_service),
):
    return await category_service.create_category(data, current_user.id)


@router.get(
    "",
    response_model=Page[CategoryResponse],
)
async def get_user_categories(
    category_status: CategoryStatus = CategoryStatus.ACTIVE,
    usable_for: TransactionType | None = None,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    category_service: CategoryService = Depends(get_category_service),
):
    return await category_service.get_user_categories(
        current_user.id, category_status, limit, offset, usable_for=usable_for
    )


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
)
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    current_user: User = Depends(get_current_user),
    category_service: CategoryService = Depends(get_category_service),
):
    return await category_service.update_category(category_id, data, current_user.id)


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_category(
    category_id: int,
    current_user: User = Depends(get_current_user),
    category_service: CategoryService = Depends(get_category_service),
):
    await category_service.archive_category(category_id, current_user.id)


@router.post("/{category_id}/restore", response_model=CategoryResponse)
async def restore_category(
    category_id: int,
    current_user: User = Depends(get_current_user),
    category_service: CategoryService = Depends(get_category_service),
):
    return await category_service.restore_category(category_id, current_user.id)
