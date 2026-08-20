from datetime import datetime, timezone
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category
from app.schemas import CategoryStatus


class CategoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, category_id: int) -> Category | None:
        return (
            await self.session.execute(select(Category).where(Category.id == category_id))
        ).scalar_one_or_none()

    async def get_by_user(
        self,
        user_id: int,
        status: CategoryStatus = CategoryStatus.ACTIVE,
    ) -> list[Category]:
        query = select(Category).where(Category.user_id == user_id)

        if status == CategoryStatus.ACTIVE:
            query = query.where(Category.archived_at.is_(None))

        elif status == CategoryStatus.ARCHIVED:
            query = query.where(Category.archived_at.is_not(None))

        result = await self.session.execute(query)

        return list(result.scalars().all())

    async def get_by_user_and_name(self, user_id: int, name: str) -> Category | None:
        return (
            await self.session.execute(
                select(Category).where(Category.user_id == user_id).where(Category.name == name)
            )
        ).scalar_one_or_none()

    async def add(self, category: Category) -> Category:
        self.session.add(category)
        await self.session.flush()

        return category

    async def update(self, category: Category) -> Category:
        await self.session.flush()

        return category

    async def archive(self, category: Category) -> None:
        category.archived_at = datetime.now(timezone.utc)

        await self.session.flush()

    async def restore(self, category: Category) -> None:
        category.archived_at = None

        await self.session.flush()
