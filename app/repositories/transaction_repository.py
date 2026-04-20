from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Transaction
from app.schemas import TransactionFilters


class TransactionRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, transaction_id: int) -> Transaction | None:
        return (
            await self.session.execute(select(Transaction).where(Transaction.id == transaction_id))
        ).scalar_one_or_none()

    async def get_by_user(
            self,
            user_id: int,
            filters: TransactionFilters,
            limit: int = 20,
            offset: int = 0,
    ) -> list[Transaction]:
        query = (select(Transaction)
                 .where(Transaction.user_id == user_id)
                 )

        if filters.type:
            query = query.where(Transaction.type == filters.type)

        if filters.currency_code:
            query = query.where(Transaction.currency_code == filters.currency_code)

        if filters.start_date:
            query = query.where(Transaction.date >= filters.start_date)

        if filters.end_date:
            query = query.where(Transaction.date <= filters.end_date)

        if filters.category_id:
            query = query.where(Transaction.category_id == filters.category_id)

        query = (query.order_by(Transaction.date.desc())
                 .offset(offset)
                 .limit(limit)
                 )

        return list((await self.session.execute(query)).scalars().all())


    async def create(self, transaction: Transaction) -> Transaction:
        self.session.add(transaction)
        await self.session.commit()
        await self.session.refresh(transaction)
        return transaction


    async def update(self, transaction: Transaction) -> Transaction:
        await self.session.commit()
        await self.session.refresh(transaction)
        return transaction


    async def delete(self, transaction: Transaction) -> None:
        await self.session.delete(transaction)
        await self.session.commit()
