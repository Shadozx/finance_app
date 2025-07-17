from fastapi import APIRouter, Depends

from src.dependencies import get_session
from src.models import Transaction
from src.schemas import TransactionOut, UnitCreate
from src.services.transaction_service import UnitService

router = APIRouter(prefix="/transactions", tags=["transactions"])

@router.get("/", response_model=list[TransactionOut])
def get_transactions(session = Depends(get_session)) -> list[TransactionOut]:
    transaction_service = UnitService(session)
    return [TransactionOut.model_validate(t) for t in transaction_service.get_all()]

@router.post("/", response_model=TransactionOut)
def create_transaction(new_transaction: UnitCreate, session = Depends(get_session)) -> TransactionOut:
    transaction = Transaction(
        **new_transaction.model_dump()
    )

    transaction_service = UnitService(session)


    return TransactionOut.model_validate(transaction_service.create(transaction))

@router.get("/{id}", response_model=TransactionOut)
def read_transaction(id: int, session = Depends(get_session)) -> TransactionOut:

    transaction_service = UnitService(session)

    return TransactionOut.model_validate(transaction_service.get_by_id(id))


@router.delete("/{id}", description="Delete a transaction")
def delete_transaction(id: int, session = Depends(get_session)):
    transaction_service = UnitService(session)

    transaction_service.delete(id)

    return {"status": "success"}