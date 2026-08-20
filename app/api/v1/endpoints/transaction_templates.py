from fastapi import APIRouter, Depends, status, Query

from app.api.dependencies import get_current_user, get_transaction_template_service
from app.services import TransactionTemplateService
from app.schemas import (
    TransactionTemplateResponse,
    TransactionTemplateCreate,
    TransactionTemplateUpdate,
)
from app.models import User

router = APIRouter(prefix="/transactions/templates", tags=["transaction templates"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TransactionTemplateResponse,
)
async def create_transaction_template(
    data: TransactionTemplateCreate,
    transaction_template_service: TransactionTemplateService = Depends(
        get_transaction_template_service
    ),
    current_user: User = Depends(get_current_user),
):
    return await transaction_template_service.create_template(data, current_user.id)


@router.get("", response_model=list[TransactionTemplateResponse])
async def get_user_transaction_templates(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    transaction_template_service: TransactionTemplateService = Depends(
        get_transaction_template_service
    ),
):
    return await transaction_template_service.get_user_templates(current_user.id, limit, offset)


@router.get("/{transaction_template_id}", response_model=TransactionTemplateResponse)
async def get_transaction_template(
    transaction_template_id: int,
    current_user: User = Depends(get_current_user),
    transaction_template_service: TransactionTemplateService = Depends(
        get_transaction_template_service
    ),
):
    return await transaction_template_service.get_template(transaction_template_id, current_user.id)


@router.put(
    "/{transaction_template_id}",
    response_model=TransactionTemplateResponse,
)
async def update_transaction_template(
    transaction_template_id: int,
    data: TransactionTemplateUpdate,
    current_user: User = Depends(get_current_user),
    transaction_template_service: TransactionTemplateService = Depends(
        get_transaction_template_service
    ),
):
    return await transaction_template_service.update_template(
        transaction_template_id, data, current_user.id
    )


@router.delete(
    "/{transaction_template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_transaction_template(
    transaction_template_id: int,
    current_user: User = Depends(get_current_user),
    transaction_template_service: TransactionTemplateService = Depends(
        get_transaction_template_service
    ),
):
    await transaction_template_service.delete_template(transaction_template_id, current_user.id)
