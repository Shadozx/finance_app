from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TransactionSplit


class TransactionSplitRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_transaction(self, transaction_id: int) -> list[TransactionSplit]:
        query = (
            select(TransactionSplit)
            .where(TransactionSplit.transaction_id == transaction_id)
            .order_by(TransactionSplit.id)
        )

        return list((await self.session.execute(query)).scalars().all())

    async def add_all(self, splits: list[TransactionSplit]) -> list[TransactionSplit]:
        self.session.add_all(splits)

        await self.session.flush()

        return splits

    async def delete_by_transaction(self, transaction_id: int) -> None:
        query = delete(TransactionSplit).where(TransactionSplit.transaction_id == transaction_id)

        await self.session.execute(query)
