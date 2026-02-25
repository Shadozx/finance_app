from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Transaction


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
            limit: int = 20,
            offset: int = 0
    ) -> list[Transaction]:
        return (
            cast(
                list[Transaction],
                (
                    await self.session.execute(
                        select(Transaction)
                        .where(Transaction.user_id == user_id)
                        .order_by(Transaction.date.desc())
                        .offset(offset)
                        .limit(limit)
                    )
                ).scalars().all()
            ))

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
