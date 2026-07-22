from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, Select, func

from decimal import Decimal

from datetime import date

from app.models import Transaction, Category, TransactionType
from app.schemas import TransactionFilters

from app.repositories.types import SummaryRow, CategorySummaryRow
from app.schemas import StatisticsFilters, CategoryStatisticsFilters


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
        query = select(Transaction).where(Transaction.user_id == user_id)

        query = self._apply_filters(query, filters)

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

    async def get_summary(
            self,
            user_id: int,
            filters: StatisticsFilters,
    ) -> list[SummaryRow]:
        query = (select(Transaction.currency_code, Transaction.type, func.sum(Transaction.amount))
                 .group_by(Transaction.currency_code, Transaction.type)
                 .where(Transaction.user_id == user_id))

        query = self._apply_filters(query, filters)

        rows = (await self.session.execute(query)).all()

        return [
            SummaryRow(currency_code=row[0], type=row[1], total=row[2])
            for row in rows
        ]

    async def get_by_category(
            self,
            user_id: int,
            filters: CategoryStatisticsFilters,
    ) -> list[CategorySummaryRow]:
        query = (select(Transaction.currency_code, Transaction.category_id, Category.name, func.sum(Transaction.amount))
                 .join(Category, Category.id == Transaction.category_id, isouter=True)
                 .group_by(Transaction.currency_code, Transaction.category_id, Category.name)
                 .where(Transaction.user_id == user_id))

        query = self._apply_filters(query, filters)

        rows = (await self.session.execute(query)).all()

        return [
            CategorySummaryRow(currency_code=row[0], category_id=row[1], category_name=row[2], total=row[3])
            for row in rows
        ]

    async def get_spent(
            self, user_id: int, category_id: int, currency_code: str,
            start_date: date, end_date: date,
    ) -> Decimal:
        query = (
            select(func.coalesce(func.sum(Transaction.amount), Decimal("0")))
            .where(Transaction.user_id == user_id)
            .where(Transaction.category_id == category_id)
            .where(Transaction.currency_code == currency_code)
            .where(Transaction.type == TransactionType.EXPENSE)
            .where(Transaction.date >= start_date)
            .where(Transaction.date <= end_date)
        )
        return (await self.session.execute(query)).scalar_one()

    def _apply_filters(
            self,
            query: Select,
            filters: TransactionFilters,
    ) -> Select:
        if filters.type is not None:
            query = query.where(Transaction.type == filters.type)

        if filters.currency_code is not None:
            query = query.where(Transaction.currency_code == filters.currency_code)

        if filters.start_date is not None:
            query = query.where(Transaction.date >= filters.start_date)

        if filters.end_date is not None:
            query = query.where(Transaction.date <= filters.end_date)

        if filters.category_id is not None:
            query = query.where(Transaction.category_id == filters.category_id)

        return query
