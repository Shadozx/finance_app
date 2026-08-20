from fastapi import APIRouter, Depends, status, Request

from app.models import User
from app.schemas import UserResponse, UsernameUpdate, PasswordUpdate
from app.api.dependencies import get_current_user, get_user_service
from app.services import UserService

from app.core.rate_limiter import limiter

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.put(
    "/me/username",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
async def update_username(
    data: UsernameUpdate,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    return await user_service.update_username(data, current_user.id)


@router.put(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("3/minute")
async def update_password(
    request: Request,
    data: PasswordUpdate,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    await user_service.update_password(data, current_user.id)
