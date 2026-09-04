from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Budget


class BudgetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, budget_id: int) -> Budget | None:
        return (
            await self.session.execute(select(Budget).where(Budget.id == budget_id))
        ).scalar_one_or_none()

    async def add(
        self,
        budget: Budget,
    ) -> Budget:
        self.session.add(budget)

        await self.session.flush()

        return budget

    async def update(self, budget: Budget) -> Budget:
        await self.session.flush()

        return budget

    async def delete(self, budget: Budget) -> None:
        await self.session.delete(budget)

    async def get_by_period(
        self,
        user_id: int,
        start_date: date,
        end_date: date,
        currency_code: str | None = None,
        category_id: int | None = None,
    ) -> list[Budget]:
        query = (
            select(Budget)
            .where(Budget.user_id == user_id)
            .where(Budget.start_date <= end_date)
            .where(Budget.end_date >= start_date)
        )

        if currency_code is not None:
            query = query.where(Budget.currency_code == currency_code)

        if category_id is not None:
            query = query.where(Budget.category_id == category_id)

        query = query.order_by(Budget.start_date, Budget.id)

        return list((await self.session.execute(query)).scalars().all())

    async def find_same_budget(
        self,
        user_id: int,
        category_id: int,
        currency_code: str,
        start_date: date,
        end_date: date,
    ) -> Budget | None:
        return (
            await self.session.execute(
                select(Budget)
                .where(Budget.user_id == user_id)
                .where(Budget.category_id == category_id)
                .where(Budget.currency_code == currency_code)
                .where(Budget.start_date == start_date)
                .where(Budget.end_date == end_date)
            )
        ).scalar_one_or_none()
