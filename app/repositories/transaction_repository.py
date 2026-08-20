from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Category, Transaction, TransactionKind, TransactionType
from app.repositories.types import CategorySummaryRow, SummaryRow, TransactionFilterProtocol
from app.schemas import CategoryStatisticsFilters, StatisticsFilters, TransactionFilters


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

        if filters.currency_code is not None:
            query = query.where(Transaction.currency_code == filters.currency_code)

        if filters.account_id is not None:
            query = query.where(Transaction.account_id == filters.account_id)

        query = query.order_by(Transaction.date.desc()).offset(offset).limit(limit)

        return list((await self.session.execute(query)).scalars().all())

    async def add(self, transaction: Transaction) -> Transaction:
        self.session.add(transaction)

        await self.session.flush()

        return transaction

    async def update(self, transaction: Transaction) -> Transaction:
        await self.session.flush()

        return transaction

    async def delete(self, transaction: Transaction) -> None:
        await self.session.delete(transaction)

    async def get_summary(
        self,
        user_id: int,
        filters: StatisticsFilters,
    ) -> list[SummaryRow]:
        query = (
            select(
                Transaction.settled_currency_code,
                Transaction.type,
                func.sum(Transaction.settled_amount),
            )
            .group_by(Transaction.settled_currency_code, Transaction.type)
            .where(Transaction.user_id == user_id)
            .where(self._counts_in_totals())
        )

        query = self._apply_filters(query, filters)

        if filters.currency_code is not None:
            query = query.where(Transaction.settled_currency_code == filters.currency_code)

        rows = (await self.session.execute(query)).all()

        return [SummaryRow(currency_code=row[0], type=row[1], total=row[2]) for row in rows]

    async def get_by_category(
        self,
        user_id: int,
        filters: CategoryStatisticsFilters,
    ) -> list[CategorySummaryRow]:
        query = (
            select(
                Transaction.settled_currency_code,
                Transaction.category_id,
                Category.name,
                func.sum(Transaction.settled_amount),
            )
            .join(Category, Category.id == Transaction.category_id, isouter=True)
            .group_by(Transaction.settled_currency_code, Transaction.category_id, Category.name)
            .where(Transaction.user_id == user_id)
            .where(self._counts_in_totals())
        )

        query = self._apply_filters(query, filters)

        if filters.currency_code is not None:
            query = query.where(Transaction.settled_currency_code == filters.currency_code)

        rows = (await self.session.execute(query)).all()

        return [
            CategorySummaryRow(
                currency_code=row[0], category_id=row[1], category_name=row[2], total=row[3]
            )
            for row in rows
        ]

    async def get_spent(
        self,
        user_id: int,
        category_id: int,
        currency_code: str,
        start_date: date,
        end_date: date,
    ) -> Decimal:
        query = (
            select(func.coalesce(func.sum(Transaction.settled_amount), Decimal("0")))
            .where(Transaction.user_id == user_id)
            .where(Transaction.category_id == category_id)
            .where(Transaction.settled_currency_code == currency_code)
            .where(Transaction.type == TransactionType.EXPENSE)
            .where(Transaction.date >= start_date)
            .where(Transaction.date <= end_date)
            .where(self._counts_in_totals())
        )
        return (await self.session.execute(query)).scalar_one()

    def _apply_filters(
        self,
        query: Select,
        filters: TransactionFilterProtocol,
    ) -> Select:
        if filters.type is not None:
            query = query.where(Transaction.type == filters.type)

        if filters.start_date is not None:
            query = query.where(Transaction.date >= filters.start_date)

        if filters.end_date is not None:
            query = query.where(Transaction.date <= filters.end_date)

        if filters.category_id is not None:
            query = query.where(Transaction.category_id == filters.category_id)

        return query

    def _counts_in_totals(self) -> ColumnElement[bool]:
        """Умова 'ця транзакція враховується в підрахунках'.

        Реєстр показує ВСІ транзакції; агрегації (статистика, бюджети,
        майбутні звіти) рахують тільки REGULAR: ADJUSTMENT — це виправлення
        залишку, TRANSFER (v1.11) — переміщення між своїми рахунками.
        Обидва не є доходом чи витратою.
        """
        return Transaction.kind == TransactionKind.REGULAR

    async def get_balance(self, account_id: int) -> Decimal:
        query = select(
            func.coalesce(
                func.sum(
                    self._signed_amount(),
                ),
                Decimal("0"),
            )
        ).where(Transaction.account_id == account_id)

        return (await self.session.execute(query)).scalar_one()

    async def get_balances_by_account(self, user_id: int) -> dict[int, Decimal]:
        query = (
            select(Transaction.account_id, func.sum(self._signed_amount()))
            .where(Transaction.user_id == user_id)
            .group_by(Transaction.account_id)
        )

        rows = (await self.session.execute(query)).all()

        return {row[0]: row[1] for row in rows}

    def _signed_amount(self) -> ColumnElement[Decimal]:
        """Signed amount in account currency: income adds, expense subtracts.

        Uses settled_amount — the balance follows money moved on this
        account, not the operation amount (24 EUR paid by a UAH card
        debits 1000 UAH).
        """
        return case(
            (Transaction.type == TransactionType.INCOME, Transaction.settled_amount),
            else_=-Transaction.settled_amount,
        )

    async def get_by_transfer_group(
        self,
        transfer_group_id: UUID,
        user_id: int,
    ) -> list[Transaction]:
        query = (
            select(Transaction)
            .where(Transaction.transfer_group_id == transfer_group_id)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.type, Transaction.id)
        )

        return list((await self.session.execute(query)).scalars().all())

    async def delete_by_transfer_group(
        self,
        transfer_group_id: UUID,
        user_id: int,
    ) -> None:
        query = (
            delete(Transaction)
            .where(Transaction.transfer_group_id == transfer_group_id)
            .where(Transaction.user_id == user_id)
        )

        await self.session.execute(query)

    async def get_counterpart_account_ids(
        self,
        transfer_group_ids: list[UUID],
        user_id: int,
    ) -> dict[int, int]:
        """Map transaction id -> account id of the other side of its transfer."""
        counterpart = aliased(Transaction)

        query = (
            select(Transaction.id, counterpart.account_id)
            .join(
                counterpart,
                and_(
                    counterpart.transfer_group_id == Transaction.transfer_group_id,
                    counterpart.id != Transaction.id,
                ),
            )
            .where(Transaction.transfer_group_id.in_(transfer_group_ids))
            .where(Transaction.user_id == user_id)
        )

        rows = (await self.session.execute(query)).all()

        return {row[0]: row[1] for row in rows}
