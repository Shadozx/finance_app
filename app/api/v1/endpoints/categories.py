from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_user, get_category_service
from app.services import CategoryService
from app.schemas import CategoryResponse, CategoryCreate, CategoryUpdate, CategoryStatus
from app.models import User

router = APIRouter(prefix="/categories", tags=["categories"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CategoryResponse
)
async def create_category(
        data: CategoryCreate,
        current_user: User = Depends(get_current_user),
        category_service: CategoryService = Depends(get_category_service)
):
    return await category_service.create_category(data, current_user.id)


@router.get(
    "",
    response_model=list[CategoryResponse],
)
async def get_user_categories(
        category_status: CategoryStatus = CategoryStatus.ACTIVE,
        current_user: User = Depends(get_current_user),
        category_service: CategoryService = Depends(get_category_service)
):
    return await category_service.get_user_categories(current_user.id, category_status)


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
)
async def update_category(
        category_id: int,
        data: CategoryUpdate,
        current_user: User = Depends(get_current_user),
        category_service: CategoryService = Depends(get_category_service)
):
    return await category_service.update_category(category_id, data, current_user.id)


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_category(
        category_id: int,
        current_user: User = Depends(get_current_user),
        category_service: CategoryService = Depends(get_category_service)
):
    await category_service.archive_category(category_id, current_user.id)


@router.post(
    "/{category_id}/restore",
    response_model=CategoryResponse
)
async def restore_category(
        category_id: int,
        current_user: User = Depends(get_current_user),
        category_service: CategoryService = Depends(get_category_service)
):
    return await category_service.restore_category(category_id, current_user.id)
