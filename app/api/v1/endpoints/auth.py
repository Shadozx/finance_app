from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_user_service
from app.services import UserService
from app.exception import ValueExistsException, AuthenticationError
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
    try:
        return await user_service.register_user(data)
    except ValueExistsException as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post(
    "/login",
    response_model=TokenResponse
)
async def login(
        data: UserLogin,
        user_service: UserService = Depends(get_user_service)
):
    try:
        token = await user_service.authenticate(data)

        return TokenResponse(access_token=token)
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e))
