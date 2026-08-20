from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import TransactionTemplate


class TransactionTemplateRepository:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session

    async def get_by_id(self, template_id: int) -> TransactionTemplate | None:
        return (
            await self.session.execute(
                select(TransactionTemplate).where(TransactionTemplate.id == template_id)
            )
        ).scalar_one_or_none()

    async def get_by_user(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> list[TransactionTemplate]:
        return list(
            (
                await self.session.execute(
                    select(TransactionTemplate)
                    .where(TransactionTemplate.user_id == user_id)
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

    async def get_by_user_and_name(
        self,
        name: str,
        user_id: int,
    ) -> TransactionTemplate | None:
        return (
            await self.session.execute(
                select(TransactionTemplate)
                .where(TransactionTemplate.user_id == user_id)
                .where(TransactionTemplate.name == name)
            )
        ).scalar_one_or_none()

    async def add(self, template: TransactionTemplate) -> TransactionTemplate:
        self.session.add(template)

        await self.session.flush()

        return template

    async def update(self, template: TransactionTemplate) -> TransactionTemplate:
        await self.session.flush()

        return template

    async def delete(self, template: TransactionTemplate) -> None:
        await self.session.delete(template)
