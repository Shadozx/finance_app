from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_current_user, get_transaction_service
from app.models import User
from app.schemas import (
    TransactionCreate,
    TransactionFilters,
    TransactionListItem,
    TransactionResponse,
    TransactionUpdate,
    UseTemplateRequest,
)
from app.services import TransactionService

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TransactionResponse,
)
async def create_transaction(
    data: TransactionCreate,
    transaction_service: TransactionService = Depends(get_transaction_service),
    current_user: User = Depends(get_current_user),
):
    return await transaction_service.create_transaction(data, current_user.id)


@router.post(
    "/from-template/{transaction_template_id}",
    status_code=status.HTTP_201_CREATED,
    response_model=TransactionResponse,
)
async def create_transaction_from_template(
    transaction_template_id: int,
    data: UseTemplateRequest,
    transaction_service: TransactionService = Depends(get_transaction_service),
    current_user: User = Depends(get_current_user),
):
    return await transaction_service.create_transaction_from_template(
        transaction_template_id, data, current_user.id
    )


@router.get("", response_model=list[TransactionListItem])
async def get_transactions(
    filters: TransactionFilters = Depends(),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    transaction_service: TransactionService = Depends(get_transaction_service),
):
    return await transaction_service.get_user_transactions(current_user.id, filters, limit, offset)


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_user),
    transaction_service: TransactionService = Depends(get_transaction_service),
):
    return await transaction_service.get_transaction(transaction_id, current_user.id)


@router.put(
    "/{transaction_id}",
    response_model=TransactionResponse,
)
async def update_transaction(
    transaction_id: int,
    data: TransactionUpdate,
    current_user: User = Depends(get_current_user),
    transaction_service: TransactionService = Depends(get_transaction_service),
):
    return await transaction_service.update_transaction(transaction_id, data, current_user.id)


@router.delete(
    "/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_user),
    transaction_service: TransactionService = Depends(get_transaction_service),
):
    await transaction_service.delete_transaction(transaction_id, current_user.id)
