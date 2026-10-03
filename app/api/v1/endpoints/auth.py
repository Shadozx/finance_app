from fastapi import APIRouter, Depends, Request, Response, status

from app.api.dependencies import get_user_service
from app.core.rate_limiter import limiter
from app.schemas import RefreshTokenRequest, TokenResponse, UserCreate, UserLogin, UserResponse
from app.services import UserService

LOGIN_REQUESTS_PER_MINUTE = 5
REFRESH_REQUESTS_PER_MINUTE = 10

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
@limiter.limit("2/minute")
async def register(
    request: Request, data: UserCreate, user_service: UserService = Depends(get_user_service)
):
    return await user_service.register_user(data)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(f"{LOGIN_REQUESTS_PER_MINUTE}/minute")
async def login(
    request: Request,
    response: Response,
    data: UserLogin,
    user_service: UserService = Depends(get_user_service),
):
    response.headers["Cache-Control"] = "no-store"

    return await user_service.authenticate(data, user_agent=request.headers.get("user-agent"))


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(f"{REFRESH_REQUESTS_PER_MINUTE}/minute")
async def refresh(
    request: Request,
    response: Response,
    data: RefreshTokenRequest,
    user_service: UserService = Depends(get_user_service),
):
    response.headers["Cache-Control"] = "no-store"

    return await user_service.refresh_session(data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    data: RefreshTokenRequest, user_service: UserService = Depends(get_user_service)
) -> None:
    await user_service.logout(data.refresh_token)
