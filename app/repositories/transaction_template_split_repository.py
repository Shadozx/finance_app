from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TransactionTemplateSplit


class TransactionTemplateSplitRepository:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session

    async def get_by_template(self, template_id: int) -> list[TransactionTemplateSplit]:
        query = (
            select(TransactionTemplateSplit)
            .where(TransactionTemplateSplit.transaction_template_id == template_id)
            .order_by(TransactionTemplateSplit.id)
        )

        return list((await self.session.execute(query)).scalars().all())

    async def get_template_ids_with_splits(self, template_ids: list[int]) -> set[int]:
        query = (
            select(TransactionTemplateSplit.transaction_template_id)
            .where(TransactionTemplateSplit.transaction_template_id.in_(template_ids))
            .distinct()
        )

        return set((await self.session.execute(query)).scalars().all())

    async def add_all(
        self, splits: list[TransactionTemplateSplit]
    ) -> list[TransactionTemplateSplit]:
        self.session.add_all(splits)

        await self.session.flush()

        return splits

    async def delete_by_template(self, template_id: int) -> None:
        query = delete(TransactionTemplateSplit).where(
            TransactionTemplateSplit.transaction_template_id == template_id
        )

        await self.session.execute(query)
