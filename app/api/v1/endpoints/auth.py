from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_user_service
from app.services import UserService
from core.exceptions import ValueExistsException, AuthenticationException
from app.schemas import UserCreate, UserResponse, UserLogin, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse
)
async def register(
        data: UserCreate,
        user_service: UserService = Depends(get_user_service)
):
    return await user_service.register_user(data)


@router.post(
    "/login",
    response_model=TokenResponse
)
async def login(
        data: UserLogin,
        user_service: UserService = Depends(get_user_service)
):
    token = await user_service.authenticate(data)

    return TokenResponse(access_token=token)
