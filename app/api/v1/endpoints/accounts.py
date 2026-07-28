from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_account_service, get_current_user
from app.models import User
from app.schemas import AccountCreate, AccountUpdate, AccountResponse, AccountStatus
from app.services import AccountService

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AccountResponse,
)
async def create_account(
        data: AccountCreate,
        account_service: AccountService = Depends(get_account_service),
        current_user: User = Depends(get_current_user),
):
    return await account_service.create_account(data, current_user.id)


@router.get(
    "",
    response_model=list[AccountResponse],
)
async def get_accounts(
        account_status: AccountStatus = AccountStatus.ACTIVE,
        current_user: User = Depends(get_current_user),
        account_service: AccountService = Depends(get_account_service),
):
    return await account_service.get_user_accounts(current_user.id, account_status)


@router.get(
    "/{account_id}",
    response_model=AccountResponse,
)
async def get_account(
        account_id: int,
        account_service: AccountService = Depends(get_account_service),
        current_user: User = Depends(get_current_user),
):
    return await account_service.get_account(account_id, current_user.id)


@router.put(
    "/{account_id}",
    response_model=AccountResponse,
)
async def update_account(
        account_id: int,
        data: AccountUpdate,
        account_service: AccountService = Depends(get_account_service),
        current_user: User = Depends(get_current_user),
):
    return await account_service.update_account(account_id, data, current_user.id)


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def archive_account(
        account_id: int,
        account_service: AccountService = Depends(get_account_service),
        current_user: User = Depends(get_current_user),
):
    await account_service.archive_account(account_id, current_user.id)


@router.post(
    "/{account_id}/restore",
    response_model=AccountResponse,
)
async def restore_account(
        account_id: int,
        account_service: AccountService = Depends(get_account_service),
        current_user: User = Depends(get_current_user),
):
    return await account_service.restore_account(account_id, current_user.id)
