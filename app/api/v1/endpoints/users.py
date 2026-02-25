from fastapi import APIRouter, Depends
from app.models import User
from app.schemas import UserResponse
from app.api.dependencies import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserResponse
)
async def get_me(
        current_user: User = Depends(get_current_user)
):
    return UserResponse.model_validate(current_user)
