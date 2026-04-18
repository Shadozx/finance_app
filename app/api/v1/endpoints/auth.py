from fastapi import APIRouter, Depends, HTTPException, status, Request

from app.api.dependencies import get_user_service
from app.services import UserService
from app.schemas import UserCreate, UserResponse, UserLogin, TokenResponse

from app.core.rate_limiter import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse
)
@limiter.limit("2/minute")
async def register(
        request: Request,
        data: UserCreate,
        user_service: UserService = Depends(get_user_service)
):
    return await user_service.register_user(data)


@router.post(
    "/login",
    response_model=TokenResponse
)
@limiter.limit("5/minute")
async def login(
        request: Request,
        data: UserLogin,
        user_service: UserService = Depends(get_user_service)
):
    token = await user_service.authenticate(data)

    return TokenResponse(access_token=token)
