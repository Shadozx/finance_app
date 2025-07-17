from sqlalchemy import select
from sqlalchemy.orm import Session

from src.exceptions import EntityNotFoundException
from src.models import Transaction


class TransactionRepository:

    def __init__(self, session: Session):
        self.session = session

    def get_all(self):
        query = select(Transaction)
        return self.session.execute(query).scalars().all()

    def get_by_id(self, id: int):
        query = select(Transaction).where(Transaction.id == id)
        result = self.session.execute(query).scalars().first()

        if result:
            return result
        else:
            raise EntityNotFoundException(entity_name="Transaction", entity_id=id)

    def save(self, transaction: Transaction):
        self.session.add(transaction)
        self.session.commit()

        self.session.refresh(transaction)

        return transaction

    def remove(self, id: int):
        transaction = self.get_by_id(id)

        self.session.delete(transaction)
        self.session.commit()
