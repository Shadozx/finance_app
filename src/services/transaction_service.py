from sqlalchemy.orm import Session

from src.models import Transaction
from src.repositories import TransactionRepository


class UnitService:

    def __init__(self, session: Session):
        self.transaction_repo = TransactionRepository(session)

    def get_all(self):
        return self.transaction_repo.get_all()

    def get_by_id(self, id: int):
        return self.transaction_repo.get_by_id(id)

    def create(self, data: Transaction):
        return self.transaction_repo.save(data)

    def delete(self, id: int):
        self.transaction_repo.remove(id)
