from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_transfer_service, get_current_user
from app.models import User
from app.schemas import TransferCreate, TransferUpdate, TransferResponse
from app.services import TransferService

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TransferResponse,
)
async def create_transfer(
    data: TransferCreate,
    transfer_service: TransferService = Depends(get_transfer_service),
    current_user: User = Depends(get_current_user),
):
    return await transfer_service.create_transfer(data, current_user.id)


@router.get(
    "/{transfer_group_id}",
    response_model=TransferResponse,
)
async def get_transfer(
    transfer_group_id: UUID,
    transfer_service: TransferService = Depends(get_transfer_service),
    current_user: User = Depends(get_current_user),
):
    return await transfer_service.get_transfer(transfer_group_id, current_user.id)


@router.put(
    "/{transfer_group_id}",
    response_model=TransferResponse,
)
async def update_transfer(
    transfer_group_id: UUID,
    data: TransferUpdate,
    transfer_service: TransferService = Depends(get_transfer_service),
    current_user: User = Depends(get_current_user),
):
    return await transfer_service.update_transfer(transfer_group_id, data, current_user.id)


@router.delete(
    "/{transfer_group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_transfer(
    transfer_group_id: UUID,
    transfer_service: TransferService = Depends(get_transfer_service),
    current_user: User = Depends(get_current_user),
):
    await transfer_service.delete_transfer(transfer_group_id, current_user.id)
