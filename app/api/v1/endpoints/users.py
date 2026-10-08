from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.dependencies import (
    AuthContext,
    get_auth_context,
    get_current_user,
    get_user_service,
    get_user_session_service,
)
from app.core.rate_limiter import limiter
from app.models import User
from app.schemas import Page, PasswordUpdate, UsernameUpdate, UserResponse, UserSessionResponse
from app.services import UserService, UserSessionService

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
    context: AuthContext = Depends(get_auth_context),
    user_service: UserService = Depends(get_user_service),
):
    await user_service.update_password(
        data, context.user.id, current_session_id=context.user_session.id
    )


@router.get("/me/sessions", response_model=Page[UserSessionResponse])
async def list_sessions(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    context: AuthContext = Depends(get_auth_context),
    user_session_service: UserSessionService = Depends(get_user_session_service),
):
    return await user_session_service.list_sessions(
        context.user.id, context.user_session.id, limit=limit, offset=offset
    )


@router.delete("/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: UUID,
    context: AuthContext = Depends(get_auth_context),
    user_session_service: UserSessionService = Depends(get_user_session_service),
):
    await user_session_service.revoke_session(context.user.id, session_id)


@router.delete("/me/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_other_sessions(
    context: AuthContext = Depends(get_auth_context),
    user_session_service: UserSessionService = Depends(get_user_session_service),
):
    await user_session_service.revoke_other_sessions(context.user.id, context.user_session.id)
