from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_transaction_service, get_current_user
from app.services import TransactionService
from app.schemas import TransactionResponse, TransactionCreate, TransactionUpdate, TransactionType
from app.models import User
from app.exception import NotAllowedActionException, NotFoundException

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
    try:
        return await transaction_service.create_transaction(current_user.id, data)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except NotAllowedActionException as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "",
    response_model=list[TransactionResponse]
)
async def get_transactions(
        limit: int = 20,
        offset: int = 0,
        current_user: User = Depends(get_current_user),
        transaction_service: TransactionService = Depends(get_transaction_service)
):
    return await transaction_service.get_user_transactions(current_user.id, limit, offset)


@router.get(
    "/{transaction_id}",
    response_model=TransactionResponse
)
async def get_transaction(
        transaction_id: int,
        current_user: User = Depends(get_current_user),
        transaction_service: TransactionService = Depends(get_transaction_service)
):
    try:
        return await transaction_service.get_transaction(transaction_id, current_user.id)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.put(
    "/{transaction_id}",
    response_model=TransactionResponse,
)
async def update_transaction(
        transaction_id: int,
        data: TransactionUpdate,
        current_user: User = Depends(get_current_user),
        transaction_service: TransactionService = Depends(get_transaction_service)
):
    try:
        return await transaction_service.update_transaction(transaction_id, current_user.id, data)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except NotAllowedActionException as e:
        raise HTTPException(status_code=409, detail=str(e))



@router.delete(
    "/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_transaction(
        transaction_id: int,
        current_user: User = Depends(get_current_user),
        transaction_service: TransactionService = Depends(get_transaction_service)
):
    try:
        await transaction_service.delete_transaction(transaction_id, current_user.id)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

