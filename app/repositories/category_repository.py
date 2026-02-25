from datetime import datetime
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Category


class CategoryRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, category_id: int) -> Category | None:
        return (
            await self.session.execute(select(Category).where(Category.id == category_id))
        ).scalar_one_or_none()

    async def get_by_user(self, user_id: int) -> list[Category]:
        return (
            cast(list[Category],
                 (
                     await self.session.execute(
                         select(Category)
                         .where(Category.user_id == user_id)
                         .where(Category.archived_at.is_(None))
                     )
                 ).scalars().all()
                 )
        )

    async def get_by_user_and_name(self, user_id: int, name: str) -> Category | None:
        return (
            await self.session.execute(
                select(Category)
                .where(Category.user_id == user_id)
                .where(Category.name == name)
            )
        ).scalar_one_or_none()

    async def create(self, category: Category) -> Category:
        self.session.add(category)
        await self.session.commit()

        await self.session.refresh(category)

        return category

    async def update(self, category: Category) -> Category:
        await self.session.commit()
        await self.session.refresh(category)

        return category

    async def archive(self, category: Category) -> None:
        category.archived_at = datetime.utcnow()

        await self.session.commit()

    async def restore(self, category: Category) -> None:
        category.archived_at = None

        await self.session.commit()
