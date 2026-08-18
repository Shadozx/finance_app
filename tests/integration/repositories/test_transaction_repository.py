from decimal import Decimal
from datetime import date
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import UserRepository, TransactionRepository, AccountRepository
from app.models import User, Transaction, TransactionType, TransactionKind, Category, Currency, Account
from app.schemas import TransactionFilters, StatisticsFilters, CategoryStatisticsFilters
from tests.integration.repositories.helpers import make_transaction


@pytest.fixture
async def transaction(
        transaction_repository: TransactionRepository,
        user: User,
        uah_account: Account,
        category: Category,
        uah_currency: Currency,
):
    return await transaction_repository.add(make_transaction(
        type=TransactionType.EXPENSE,
        kind=TransactionKind.REGULAR,
        description="Morning Coffee",
        amount=Decimal("100.00"),
        currency_code=uah_currency.code,
        category_id=category.id,
        user_id=user.id,
        account_id=uah_account.id,
        date=date(2025, 3, 1)
    ))


class TestAdd:

    async def test_add(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            category: Category,
            uah_currency: Currency,
    ):
        transaction = make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            description="Morning Coffee",
            amount=Decimal("100.00"),
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2025, 3, 1)
        )

        created_transaction = await transaction_repository.add(transaction)

        assert created_transaction.id is not None

        assert created_transaction.type == transaction.type
        assert created_transaction.description == transaction.description
        assert created_transaction.amount == transaction.amount
        assert created_transaction.currency_code == transaction.currency_code
        assert created_transaction.settled_amount == transaction.settled_amount
        assert created_transaction.settled_currency_code == transaction.settled_currency_code
        assert created_transaction.category_id == transaction.category_id
        assert created_transaction.user_id == transaction.user_id
        assert created_transaction.account_id == transaction.account_id
        assert created_transaction.date == transaction.date
        assert created_transaction.created_at is not None
        assert created_transaction.updated_at is not None


class TestGetById:

    async def test_get_by_id(
            self,
            transaction_repository: TransactionRepository,
            transaction: Transaction,
    ):
        found_transaction = await transaction_repository.get_by_id(transaction.id)

        assert found_transaction.id == transaction.id
        assert found_transaction.type == transaction.type
        assert found_transaction.user_id == transaction.user_id

    async def test_get_by_id_not_found(
            self,
            transaction_repository: TransactionRepository,
    ):
        found_transaction = await transaction_repository.get_by_id(999)

        assert found_transaction is None


class TestGetByUser:
    async def test_get_by_user(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            transaction: Transaction,
            uah_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            description="Foods",
            amount=Decimal("550.00"),
            currency_code=uah_currency.code,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2025, 3, 3)
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("35000.00"),
            description="Salary",
            currency_code=uah_currency.code,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2026, 1, 15),
        ))

        transactions = await transaction_repository.get_by_user(user.id, TransactionFilters())

        assert len(transactions) == 3

        assert all(t.user_id == user.id for t in transactions)

    async def test_get_by_user_empty(
            self,
            test_session: AsyncSession,
            transaction_repository: TransactionRepository,
            user: User,
    ):
        transactions = await transaction_repository.get_by_user(user.id, TransactionFilters())

        assert len(transactions) == 0

    async def test_get_by_user_returns_only_own(
            self,
            test_session: AsyncSession,
            transaction_repository: TransactionRepository,
            account_repository: AccountRepository,
            user: User,
            transaction: Transaction,
            usd_currency: Currency,
    ):
        other_user_repository = UserRepository(test_session)
        other_user = await other_user_repository.add(User(
            email="other@test.com",
            username="other",
            hashed_password="hashed",
        ))

        other_account = await account_repository.add(
            Account(
                name="Other user account",
                currency_code=usd_currency.code,
                user_id=other_user.id
            )
        )

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("50.00"),
            description="Netflix",
            currency_code=usd_currency.code,
            user_id=other_user.id,
            account_id=other_account.id,
            date=date(2026, 2, 15),
        ))

        transactions = await transaction_repository.get_by_user(user.id, TransactionFilters())

        assert len(transactions) == 1

        assert transactions[0].id == transaction.id
        assert transactions[0].description == transaction.description
        assert transactions[0].user_id == transaction.user_id
        assert transactions[0].account_id == transaction.account_id

    async def test_get_by_user_ordered_by_date_desc(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            uah_currency: Currency,
    ):
        t_old = await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="Old",
            currency_code=uah_currency.code,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2026, 1, 1),
        ))

        t_new = await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("200.00"),
            description="New",
            currency_code=uah_currency.code,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2026, 3, 1),
        ))

        t_mid = await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("150.00"),
            description="Mid",
            currency_code=uah_currency.code,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2026, 2, 1),
        ))

        transactions = await transaction_repository.get_by_user(
            user.id, TransactionFilters()
        )

        assert transactions[0].id == t_new.id  # March
        assert transactions[1].id == t_mid.id  # February
        assert transactions[2].id == t_old.id  # January


@pytest.fixture
async def transactions(
        transaction_repository: TransactionRepository,
        user: User,
        uah_account: Account,
        usd_account: Account,
        uah_currency: Currency,
        usd_currency: Currency,
        category: Category
):
    t1 = await transaction_repository.add(make_transaction(
        type=TransactionType.INCOME,
        kind=TransactionKind.REGULAR,
        amount=Decimal("10000.00"),
        description="Salary",
        currency_code=usd_currency.code,
        user_id=user.id,
        category_id=category.id,
        account_id=usd_account.id,
        date=date(2026, 1, 15),
    ))

    t2 = await transaction_repository.add(make_transaction(
        type=TransactionType.EXPENSE,
        kind=TransactionKind.REGULAR,
        amount=Decimal("150.00"),
        description="Coffee",
        currency_code=uah_currency.code,
        user_id=user.id,
        category_id=category.id,
        account_id=uah_account.id,
        date=date(2026, 2, 10),
    ))

    t3 = await transaction_repository.add(make_transaction(
        type=TransactionType.EXPENSE,
        kind=TransactionKind.REGULAR,
        amount=Decimal("50.00"),
        description="Netflix",
        currency_code=usd_currency.code,
        user_id=user.id,
        category_id=None,
        account_id=usd_account.id,
        date=date(2026, 2, 15),
    ))

    t4 = await transaction_repository.add(make_transaction(
        type=TransactionType.INCOME,
        kind=TransactionKind.REGULAR,
        amount=Decimal("500.00"),
        description="Freelance",
        currency_code=usd_currency.code,
        user_id=user.id,
        category_id=None,
        account_id=usd_account.id,
        date=date(2026, 3, 1),
    ))

    t5 = await transaction_repository.add(make_transaction(
        type=TransactionType.EXPENSE,
        kind=TransactionKind.REGULAR,
        amount=Decimal("200.00"),
        description="Lunch",
        currency_code=uah_currency.code,
        user_id=user.id,
        category_id=category.id,
        account_id=uah_account.id,
        date=date(2026, 3, 10),
    ))

    return [t1, t2, t3, t4, t5]


class TestPagination:

    async def test_pagination_limit(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transactions
    ):
        limit = 2
        user_transactions = await transaction_repository.get_by_user(user.id, TransactionFilters(), limit=limit)

        assert len(user_transactions) == limit

    async def test_pagination_offset(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transactions
    ):
        offset = 2
        user_transactions = await transaction_repository.get_by_user(user.id, TransactionFilters(), offset=offset)

        assert len(user_transactions) == 3


class TestFilters:

    async def test_filter_by_type(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transactions
    ):
        user_transactions = await transaction_repository.get_by_user(user.id,
                                                                     TransactionFilters(type=TransactionType.EXPENSE))

        assert len(user_transactions) == 3

        assert all(t.type == TransactionType.EXPENSE for t in user_transactions)

    async def test_filter_by_currency_code(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transactions,
            uah_currency: Currency
    ):
        user_transactions = await transaction_repository.get_by_user(user.id,
                                                                     TransactionFilters(
                                                                         currency_code=uah_currency.code))

        assert len(user_transactions) == 2
        assert all(t.currency_code == uah_currency.code for t in user_transactions)

    async def test_filter_by_category_id(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transactions,
            category: Category
    ):
        user_transactions = await transaction_repository.get_by_user(user.id,
                                                                     TransactionFilters(category_id=category.id))

        assert len(user_transactions) == 3

        assert all(t.category_id == category.id for t in user_transactions)

    async def test_filter_by_date_range(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transactions
    ):
        start_date = date(2026, 1, 15)
        end_date = date(2026, 2, 15)

        user_transactions = await transaction_repository.get_by_user(user.id, TransactionFilters(start_date=start_date,
                                                                                                 end_date=end_date))

        assert len(user_transactions) == 3

        assert all((start_date <= t.date <= end_date) for t in user_transactions)

    async def test_filter_by_account_id(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            transactions,
    ):
        user_transactions = await transaction_repository.get_by_user(
            user.id, TransactionFilters(account_id=uah_account.id)
        )

        assert len(user_transactions) == 2

        assert all(t.account_id == uah_account.id for t in user_transactions)

    async def test_filter_combined(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transactions,
            uah_currency: Currency
    ):
        user_transactions = await transaction_repository.get_by_user(user.id,
                                                                     TransactionFilters(currency_code=uah_currency.code,
                                                                                        type=TransactionType.EXPENSE))

        assert len(user_transactions) == 2

        assert all(
            t.type == TransactionType.EXPENSE and t.currency_code == uah_currency.code for t in user_transactions
        )


class TestUpdate:
    async def test_update(
            self,
            transaction_repository: TransactionRepository,
            transaction: Transaction
    ):
        created_at = transaction.created_at
        updated_at_old = transaction.updated_at

        transaction.amount = Decimal("155.00")

        updated_transaction = await transaction_repository.update(transaction)

        assert updated_transaction.id == transaction.id
        assert updated_transaction.amount == transaction.amount

        found_transaction = await transaction_repository.get_by_id(transaction.id)

        assert found_transaction.amount == transaction.amount
        assert found_transaction.created_at == created_at
        assert found_transaction.updated_at > updated_at_old


class TestDelete:
    async def test_delete(
            self,
            transaction_repository: TransactionRepository,
            transaction: Transaction
    ):
        await transaction_repository.delete(transaction)

        found_transaction = await transaction_repository.get_by_id(transaction.id)
        assert found_transaction is None


class TestGetSummary:
    async def test_get_summary(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transactions,
            uah_currency: Currency,
            usd_currency: Currency
    ):
        summary = await transaction_repository.get_summary(
            user.id,
            StatisticsFilters(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31)
            )
        )

        assert len(summary) == 3

        totals = {(row.currency_code, row.type): row.total for row in summary}

        assert totals[(uah_currency.code, TransactionType.EXPENSE)] == Decimal("350.00")
        assert totals[(usd_currency.code, TransactionType.EXPENSE)] == Decimal("50.00")
        assert totals[(usd_currency.code, TransactionType.INCOME)] == Decimal("10500.00")

        assert (uah_currency.code, TransactionType.INCOME) not in totals

    async def test_get_summary_empty(
            self,
            transaction_repository: TransactionRepository,
            user: User,
    ):
        summary = await transaction_repository.get_summary(
            user.id,
            StatisticsFilters(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31)
            )
        )

        assert len(summary) == 0

    async def test_get_summary_returns_only_own(
            self,
            account_repository: AccountRepository,
            transaction_repository: TransactionRepository,
            user_repository: UserRepository,
            user: User,
            transactions,
            usd_currency: Currency,
            uah_currency: Currency,
    ):
        other_user = await user_repository.add(User(
            email="otheruser@test.com",
            username="otheruser",
            hashed_password="hashed_password",
        ))

        other_account = await account_repository.add(
            Account(
                name="Other user account",
                currency_code=uah_currency.code,
                user_id=other_user.id
            )
        )

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("999.00"),
            description="Other user expense",
            currency_code=uah_currency.code,
            user_id=other_user.id,
            category_id=None,
            account_id=other_account.id,
            date=date(2026, 2, 20),
        ))

        summary = await transaction_repository.get_summary(
            user.id,
            StatisticsFilters(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31)
            )
        )

        assert len(summary) == 3

        totals = {(row.currency_code, row.type): row.total for row in summary}

        assert totals[(uah_currency.code, TransactionType.EXPENSE)] == Decimal("350.00")
        assert totals[(usd_currency.code, TransactionType.EXPENSE)] == Decimal("50.00")
        assert totals[(usd_currency.code, TransactionType.INCOME)] == Decimal("10500.00")

    async def test_get_summary_filter_by_date_range(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transactions,
            usd_currency: Currency,
    ):
        summary = await transaction_repository.get_summary(
            user.id,
            StatisticsFilters(
                currency_code=usd_currency.code,
                type=TransactionType.INCOME,
                start_date=date(2026, 1, 15),
                end_date=date(2026, 2, 15),
            )

        )

        assert len(summary) == 1

        usd_income_summary = summary[0]

        assert usd_income_summary.type == TransactionType.INCOME
        assert usd_income_summary.currency_code == usd_currency.code
        assert usd_income_summary.total == Decimal("10000.00")

    async def test_get_summary_with_type_filter(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transactions,
            uah_currency: Currency,
            usd_currency: Currency
    ):
        summary = await transaction_repository.get_summary(
            user.id,
            StatisticsFilters(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
                type=TransactionType.EXPENSE
            )
        )

        assert len(summary) == 2

        totals = {(row.currency_code, row.type): row.total for row in summary}

        assert totals[(uah_currency.code, TransactionType.EXPENSE)] == Decimal("350.00")
        assert totals[(usd_currency.code, TransactionType.EXPENSE)] == Decimal("50.00")

        assert (uah_currency.code, TransactionType.INCOME) not in totals
        assert (usd_currency.code, TransactionType.INCOME) not in totals

    async def test_get_summary_filter_by_category(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            usd_account: Account,
            transactions,
            category: Category,
            uah_currency: Currency,
            usd_currency: Currency,
    ):
        await transaction_repository.add(
            make_transaction(
                type=TransactionType.INCOME,
                kind=TransactionKind.REGULAR,
                amount=Decimal("450.00"),
                description="Refund from a friend",
                currency_code=uah_currency.code,
                user_id=user.id,
                category_id=category.id,
                account_id=uah_account.id,
                date=date(2026, 3, 1),
            ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("75.00"),
            description="Gym membership",
            currency_code=usd_currency.code,
            user_id=user.id,
            category_id=category.id,
            account_id=usd_account.id,
            date=date(2026, 1, 20),
        ))

        summary = await transaction_repository.get_summary(
            user.id,
            StatisticsFilters(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
                category_id=category.id
            )
        )

        assert len(summary) == 4

        totals = {(row.currency_code, row.type): row.total for row in summary}

        assert totals[(uah_currency.code, TransactionType.EXPENSE)] == Decimal("350.00")
        assert totals[(uah_currency.code, TransactionType.INCOME)] == Decimal("450.00")
        assert totals[(usd_currency.code, TransactionType.EXPENSE)] == Decimal("75.00")
        assert totals[(usd_currency.code, TransactionType.INCOME)] == Decimal("10000.00")

    async def test_get_summary_excludes_adjustment(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            uah_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="Salary",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.ADJUSTMENT,
            amount=Decimal("5000.00"),
            description="Opening balance",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        summary = await transaction_repository.get_summary(
            user.id,
            StatisticsFilters(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            )
        )

        assert len(summary) == 1

        totals = {(row.currency_code, row.type): row.total for row in summary}

        assert totals[(uah_currency.code, TransactionType.INCOME)] == Decimal("100.00")

    async def test_get_summary_excludes_transfer(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            usd_account: Account,
            uah_currency: Currency,
            usd_currency: Currency,
    ):
        group_id = uuid.uuid4()

        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="Salary",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.TRANSFER,
            amount=Decimal("1000.00"),
            description="Transfer out",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            transfer_group_id=group_id,
            date=date(2026, 2, 11),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.TRANSFER,
            amount=Decimal("24.00"),
            description="Transfer in",
            currency_code=usd_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=usd_account.id,
            transfer_group_id=group_id,
            date=date(2026, 2, 11),
        ))

        summary = await transaction_repository.get_summary(
            user.id,
            StatisticsFilters(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            )
        )

        assert len(summary) == 1

        totals = {(row.currency_code, row.type): row.total for row in summary}

        assert totals[(uah_currency.code, TransactionType.INCOME)] == Decimal("100.00")

    async def test_get_summary_uses_settled_amount(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            uah_currency: Currency,
            usd_currency: Currency,
    ):
        """A USD purchase on a UAH card falls into the UAH group, by the settled amount."""
        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            description="USD purchase on a UAH card",
            amount=Decimal("24.00"),
            currency_code=usd_currency.code,
            settled_currency_code=uah_currency.code,
            settled_amount=Decimal("1000.00"),
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        summary = await transaction_repository.get_summary(
            user.id,
            StatisticsFilters(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            )
        )

        assert len(summary) == 1

        totals = {(row.currency_code, row.type): row.total for row in summary}

        assert totals[(uah_currency.code, TransactionType.EXPENSE)] == Decimal("1000.00")


class TestGetByCategory:
    async def test_get_by_category(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transactions,
            category: Category,
            uah_currency: Currency,
    ):
        summary = await transaction_repository.get_by_category(
            user.id,
            CategoryStatisticsFilters(
                type=TransactionType.EXPENSE,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31)
            ),
        )

        assert len(summary) == 2

        totals = {(row.currency_code, row.category_id): row for row in summary}

        assert totals[("UAH", category.id)].total == Decimal("350.00")
        assert totals[("UAH", category.id)].category_name == category.name
        assert totals[("USD", None)].total == Decimal("50.00")
        assert totals[("USD", None)].category_name is None

        assert ("UAH", None) not in totals
        assert ("USD", category.id) not in totals

    async def test_get_by_category_does_not_mix_types(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            category: Category,
            uah_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("10000.00"),
            description="Salary",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=category.id,
            account_id=uah_account.id,
            date=date(2026, 1, 15),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("300.00"),
            description="Coffee",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=category.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        summary = await transaction_repository.get_by_category(
            user.id,
            CategoryStatisticsFilters(
                type=TransactionType.EXPENSE,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            )
        )

        assert len(summary) == 1

        totals = {(row.currency_code, row.category_id): row for row in summary}

        assert totals[("UAH", category.id)].total == Decimal("300.00")

        summary = await transaction_repository.get_by_category(
            user.id,
            CategoryStatisticsFilters(
                type=TransactionType.INCOME,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            )
        )

        assert len(summary) == 1

        totals = {(row.currency_code, row.category_id): row for row in summary}

        assert totals[("UAH", category.id)].total == Decimal("10000.00")

    async def test_get_by_category_groups_uncategorized_together(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            uah_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("250.00"),
            description="Ice cream",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 1, 15),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="Coffee",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        summary = await transaction_repository.get_by_category(
            user.id,
            CategoryStatisticsFilters(
                type=TransactionType.EXPENSE,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            )
        )

        assert len(summary) == 1

        totals = {(row.currency_code, row.category_id): row for row in summary}

        assert totals[("UAH", None)].total == Decimal("350.00")
        assert totals[("UAH", None)].category_name is None
        assert totals[("UAH", None)].category_id is None

    async def test_get_by_category_returns_only_own(
            self,
            user_repository: UserRepository,
            account_repository: AccountRepository,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            uah_currency: Currency,
            category: Category,
    ):
        other_user = await user_repository.add(User(
            email="otheruser@test.com",
            username="otheruser",
            hashed_password="hashed_password",
        ))

        other_account = await account_repository.add(
            Account(
                name="Other user account",
                currency_code=uah_currency.code,
                user_id=other_user.id
            )
        )

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("999.00"),
            description="Other user expense",
            currency_code=uah_currency.code,
            user_id=other_user.id,
            category_id=None,
            account_id=other_account.id,
            date=date(2026, 2, 20),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("150.00"),
            description="Coffee",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=category.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        summary = await transaction_repository.get_by_category(
            user.id,
            CategoryStatisticsFilters(
                type=TransactionType.EXPENSE,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            )
        )

        assert len(summary) == 1

        totals = {(row.currency_code, row.category_id): row for row in summary}

        assert totals[("UAH", category.id)].total == Decimal("150.00")

    async def test_get_by_category_uses_settled_amount(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            category: Category,
            uah_currency: Currency,
            usd_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            description="USD purchase on a UAH card",
            amount=Decimal("24.00"),
            currency_code=usd_currency.code,
            settled_amount=Decimal("1000.00"),
            settled_currency_code=uah_currency.code,
            user_id=user.id,
            category_id=category.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        summary = await transaction_repository.get_by_category(
            user.id,
            CategoryStatisticsFilters(
                type=TransactionType.EXPENSE,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            )
        )

        assert len(summary) == 1

        totals = {(row.currency_code, row.category_id): row for row in summary}

        assert totals[(uah_currency.code, category.id)].total == Decimal("1000.00")

    async def test_get_by_category_empty(
            self,
            transaction_repository: TransactionRepository,
            user: User,
    ):
        summary = await transaction_repository.get_by_category(
            user.id,
            CategoryStatisticsFilters(
                type=TransactionType.EXPENSE,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31)
            )
        )

        assert len(summary) == 0

    async def test_get_by_category_excludes_adjustment(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            category: Category,
            uah_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="Coffee",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=category.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.ADJUSTMENT,
            amount=Decimal("5000.00"),
            description="Opening balance",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=category.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        summary = await transaction_repository.get_by_category(
            user.id,
            CategoryStatisticsFilters(
                type=TransactionType.EXPENSE,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            )
        )

        assert len(summary) == 1

        totals = {(row.currency_code, row.category_id): row for row in summary}

        assert totals[("UAH", category.id)].total == Decimal("100.00")
        assert totals[("UAH", category.id)].category_name == category.name

    async def test_get_by_category_excludes_transfer(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            category: Category,
            uah_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="Coffee",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=category.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.TRANSFER,
            amount=Decimal("5000.00"),
            description="Transfer out",
            currency_code=uah_currency.code,
            user_id=user.id,
            # category_id is intentionally not None: a real transfer has NULL here,
            # but then the row would be filtered out by category, not by kind —
            # and the test would stop guarding _counts_in_totals()
            category_id=category.id,
            account_id=uah_account.id,
            transfer_group_id=uuid.uuid4(),
            date=date(2026, 2, 10),
        ))

        summary = await transaction_repository.get_by_category(
            user.id,
            CategoryStatisticsFilters(
                type=TransactionType.EXPENSE,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            )
        )

        assert len(summary) == 1

        totals = {(row.currency_code, row.category_id): row for row in summary}

        assert totals[("UAH", category.id)].total == Decimal("100.00")
        assert totals[("UAH", category.id)].category_name == category.name


class TestGetSpent:
    async def test_get_spent(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transactions,
            category: Category,
            uah_currency: Currency,
    ):
        spent = await transaction_repository.get_spent(
            user.id,
            category.id,
            uah_currency.code,
            date(2026, 1, 1),
            date(2026, 3, 31),
        )

        assert spent == Decimal("350.00")

    async def test_get_spent_ignores_income(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            category: Category,
            uah_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("500.00"),
            description="Coffee",
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("10000.00"),
            description="Salary",
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2026, 2, 15),
        ))

        spent = await transaction_repository.get_spent(
            user.id,
            category.id,
            uah_currency.code,
            date(2026, 1, 1),
            date(2026, 3, 31),
        )

        assert spent == Decimal("500.00")

    async def test_get_spent_filters_category_currency_dates(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            usd_account: Account,
            category: Category,
            uah_currency: Currency,
            usd_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("300.00"),
            description="Target",
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("40.00"),
            description="Other currency",
            currency_code=usd_currency.code,
            category_id=category.id,
            user_id=user.id,
            account_id=usd_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("999.00"),
            description="Uncategorized",
            currency_code=uah_currency.code,
            category_id=None,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("888.00"),
            description="Out of range",
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2026, 5, 1),
        ))

        spent = await transaction_repository.get_spent(
            user.id,
            category.id,
            uah_currency.code,
            date(2026, 2, 1),
            date(2026, 2, 28),
        )

        assert spent == Decimal("300.00")

    async def test_get_spent_empty_returns_zero(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            category: Category,
            uah_currency: Currency,
    ):
        spent = await transaction_repository.get_spent(
            user.id,
            category.id,
            uah_currency.code,
            date(2026, 1, 1),
            date(2026, 3, 31),
        )

        assert spent == Decimal("0")

    async def test_get_spent_returns_only_own(
            self,
            account_repository: AccountRepository,
            transaction_repository: TransactionRepository,
            user_repository: UserRepository,
            user: User,
            uah_account: Account,
            category: Category,
            uah_currency: Currency,
    ):
        other_user = await user_repository.add(User(
            email="otherspent@test.com",
            username="otherspent",
            hashed_password="hashed_password",
        ))

        other_account = await account_repository.add(
            Account(
                name="Other user account",
                currency_code=uah_currency.code,
                user_id=other_user.id
            )
        )

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("777.00"),
            description="Other user expense",
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=other_user.id,
            account_id=other_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="Own expense",
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2026, 2, 12),
        ))

        spent = await transaction_repository.get_spent(
            user.id,
            category.id,
            uah_currency.code,
            date(2026, 1, 1),
            date(2026, 3, 31),
        )

        assert spent == Decimal("100.00")

    async def test_get_spent_excludes_adjustment(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            category: Category,
            uah_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="Coffee",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=category.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.ADJUSTMENT,
            amount=Decimal("5000.00"),
            description="Opening balance",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=category.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        spent = await transaction_repository.get_spent(
            user.id,
            category.id,
            uah_currency.code,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),

        )

        assert spent == Decimal("100.00")

    async def test_get_spent_excludes_transfer(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            category: Category,
            uah_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="Coffee",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=category.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.TRANSFER,
            amount=Decimal("5000.00"),
            description="Transfer out",
            currency_code=uah_currency.code,
            user_id=user.id,
            # category_id is intentionally not None: a real transfer has NULL here,
            # but then the row would be filtered out by category, not by kind —
            # and the test would stop guarding _counts_in_totals()
            category_id=category.id,
            account_id=uah_account.id,
            transfer_group_id=uuid.uuid4(),
            date=date(2026, 2, 10),
        ))

        spent = await transaction_repository.get_spent(
            user.id,
            category.id,
            uah_currency.code,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )

        assert spent == Decimal("100.00")

    async def test_get_spent_uses_settled_amount(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            uah_currency: Currency,
            usd_currency: Currency,
            category: Category,
    ):
        """A USD purchase on a UAH card counts toward a UAH budget, by the settled amount."""
        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            description="USD purchase on a UAH card",
            amount=Decimal("24.00"),
            currency_code=usd_currency.code,
            settled_currency_code=uah_currency.code,
            settled_amount=Decimal("1000.00"),
            user_id=user.id,
            category_id=category.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        spent = await transaction_repository.get_spent(
            user.id,
            category.id,
            uah_currency.code,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )

        assert spent == Decimal("1000.00")


class TestGetBalance:
    async def test_get_balance_empty_account_returns_zero(
            self,
            transaction_repository: TransactionRepository,
            uah_account: Account,
    ):
        balance = await transaction_repository.get_balance(uah_account.id)

        assert balance == Decimal("0")

    async def test_get_balance_income_adds_expense_subtracts(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            uah_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("1000.00"),
            description="Salary",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("300.00"),
            description="Coffee",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 11),
        ))

        balance = await transaction_repository.get_balance(uah_account.id)

        assert balance == Decimal("700.00")

    async def test_get_balance_includes_adjustment(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            uah_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.ADJUSTMENT,
            amount=Decimal("5000.00"),
            description="Opening balance",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="Coffee",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 11),
        ))

        balance = await transaction_repository.get_balance(uah_account.id)

        assert balance == Decimal("4900.00")

    async def test_get_balance_includes_future_dates(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            uah_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="Future income",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2099, 1, 1),
        ))

        balance = await transaction_repository.get_balance(uah_account.id)

        assert balance == Decimal("100.00")

    async def test_get_balance_returns_only_own_account(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            usd_account: Account,
            uah_currency: Currency,
            usd_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="UAH income",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("999.00"),
            description="USD income",
            currency_code=usd_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=usd_account.id,
            date=date(2026, 2, 10),
        ))

        balance = await transaction_repository.get_balance(uah_account.id)

        assert balance == Decimal("100.00")

    async def test_get_balance_uses_settled_amount(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            uah_currency: Currency,
            usd_currency: Currency,
    ):
        """A USD purchase on a UAH card: the balance moves by what the account was charged."""
        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            description="USD purchase on a UAH card",
            amount=Decimal("24.00"),
            currency_code=usd_currency.code,
            settled_currency_code=uah_currency.code,
            settled_amount=Decimal("1000.00"),
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        balance = await transaction_repository.get_balance(uah_account.id)

        assert balance == Decimal("-1000.00")


class TestGetBalancesByAccount:
    async def test_get_balances_by_account(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            usd_account: Account,
            uah_currency: Currency,
            usd_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("1000.00"),
            description="Salary",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("300.00"),
            description="Coffee",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 11),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("50.00"),
            description="Refund",
            currency_code=usd_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=usd_account.id,
            date=date(2026, 2, 12),
        ))

        balances = await transaction_repository.get_balances_by_account(user.id)

        assert balances[uah_account.id] == Decimal("700.00")
        assert balances[usd_account.id] == Decimal("50.00")

    async def test_get_balances_by_account_skips_accounts_without_transactions(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            usd_account: Account,
            uah_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="Salary",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        balances = await transaction_repository.get_balances_by_account(user.id)

        assert balances[uah_account.id] == Decimal("100.00")
        assert usd_account.id not in balances

    async def test_get_balances_by_account_returns_only_own(
            self,
            transaction_repository: TransactionRepository,
            user_repository: UserRepository,
            account_repository: AccountRepository,
            user: User,
            uah_account: Account,
            uah_currency: Currency,
    ):
        other_user = await user_repository.add(User(
            email="otherbalance@test.com",
            username="otherbalance",
            hashed_password="hashed_password",
        ))

        other_account = await account_repository.add(Account(
            name="Other user account",
            currency_code=uah_currency.code,
            user_id=other_user.id,
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("999.00"),
            description="Other user income",
            currency_code=uah_currency.code,
            user_id=other_user.id,
            category_id=None,
            account_id=other_account.id,
            date=date(2026, 2, 10),
        ))

        await transaction_repository.add(make_transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("100.00"),
            description="Own income",
            currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        balances = await transaction_repository.get_balances_by_account(user.id)

        assert balances[uah_account.id] == Decimal("100.00")
        assert other_account.id not in balances

    async def test_get_balances_by_account_uses_settled_amount(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            uah_currency: Currency,
            usd_currency: Currency,
    ):
        await transaction_repository.add(make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            description="USD purchase on a UAH card",
            amount=Decimal("24.00"),
            currency_code=usd_currency.code,
            settled_amount=Decimal("1000.00"),
            settled_currency_code=uah_currency.code,
            user_id=user.id,
            category_id=None,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        ))

        balances = await transaction_repository.get_balances_by_account(user.id)

        assert balances[uah_account.id] == Decimal("-1000.00")


@pytest.fixture
async def transfer(
        transaction_repository: TransactionRepository,
        user: User,
        uah_account: Account,
        usd_account: Account,
        uah_currency: Currency,
        usd_currency: Currency,
):
    """A cross-currency transfer pair: 1000 UAH out, 24 USD in."""
    group_id = uuid.uuid4()

    from_side = await transaction_repository.add(make_transaction(
        type=TransactionType.EXPENSE,
        kind=TransactionKind.TRANSFER,
        amount=Decimal("1000.00"),
        description="Transfer",
        currency_code=uah_currency.code,
        user_id=user.id,
        category_id=None,
        account_id=uah_account.id,
        transfer_group_id=group_id,
        date=date(2026, 2, 10),
    ))

    to_side = await transaction_repository.add(make_transaction(
        type=TransactionType.INCOME,
        kind=TransactionKind.TRANSFER,
        amount=Decimal("24.00"),
        description="Transfer",
        currency_code=usd_currency.code,
        user_id=user.id,
        category_id=None,
        account_id=usd_account.id,
        transfer_group_id=group_id,
        date=date(2026, 2, 10),
    ))

    return from_side, to_side


class TestGetByTransferGroup:
    async def test_get_by_transfer_group_returns_both_sides(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transfer,
    ):
        from_side, to_side = transfer

        sides = await transaction_repository.get_by_transfer_group(
            from_side.transfer_group_id, user.id
        )

        assert len(sides) == 2
        assert {side.id for side in sides} == {from_side.id, to_side.id}

    async def test_get_by_transfer_group_unknown_group_returns_empty(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transfer,
    ):
        sides = await transaction_repository.get_by_transfer_group(uuid.uuid4(), user.id)

        assert sides == []

    async def test_get_by_transfer_group_returns_only_own(
            self,
            transaction_repository: TransactionRepository,
            user_repository: UserRepository,
            transfer,
    ):
        from_side, _ = transfer

        other_user = await user_repository.add(User(
            email="othertransfer@test.com",
            username="othertransfer",
            hashed_password="hashed_password",
        ))

        sides = await transaction_repository.get_by_transfer_group(
            from_side.transfer_group_id, other_user.id
        )

        assert sides == []


class TestDeleteByTransferGroup:
    async def test_delete_by_transfer_group_removes_both_sides(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transfer,
    ):
        from_side, to_side = transfer

        await transaction_repository.delete_by_transfer_group(
            from_side.transfer_group_id, user.id
        )

        assert await transaction_repository.get_by_id(from_side.id) is None
        assert await transaction_repository.get_by_id(to_side.id) is None

    async def test_delete_by_transfer_group_keeps_other_transactions(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transaction: Transaction,
            transfer,
    ):
        from_side, _ = transfer

        await transaction_repository.delete_by_transfer_group(
            from_side.transfer_group_id, user.id
        )

        assert await transaction_repository.get_by_id(transaction.id) is not None

    async def test_delete_by_transfer_group_does_not_delete_other_users_group(
            self,
            transaction_repository: TransactionRepository,
            user_repository: UserRepository,
            transfer,
    ):
        from_side, to_side = transfer

        other_user = await user_repository.add(User(
            email="otherdelete@test.com",
            username="otherdelete",
            hashed_password="hashed_password",
        ))

        await transaction_repository.delete_by_transfer_group(
            from_side.transfer_group_id, other_user.id
        )

        assert await transaction_repository.get_by_id(from_side.id) is not None
        assert await transaction_repository.get_by_id(to_side.id) is not None


class TestGetCounterpartAccountIds:
    async def test_get_counterpart_account_ids_maps_each_side_to_the_other(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_account: Account,
            usd_account: Account,
            transfer,
    ):
        from_side, to_side = transfer

        counterparts = await transaction_repository.get_counterpart_account_ids(
            [from_side.transfer_group_id], user.id
        )

        assert counterparts[from_side.id] == usd_account.id
        assert counterparts[to_side.id] == uah_account.id

    async def test_get_counterpart_account_ids_ignores_regular_transactions(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            transaction: Transaction,
            transfer,
    ):
        from_side, _ = transfer

        counterparts = await transaction_repository.get_counterpart_account_ids(
            [from_side.transfer_group_id], user.id
        )

        assert transaction.id not in counterparts

    async def test_get_counterpart_account_ids_returns_only_own(
            self,
            transaction_repository: TransactionRepository,
            user_repository: UserRepository,
            transfer,
    ):
        from_side, _ = transfer

        other_user = await user_repository.add(User(
            email="othercounterpart@test.com",
            username="othercounterpart",
            hashed_password="hashed_password",
        ))

        counterparts = await transaction_repository.get_counterpart_account_ids(
            [from_side.transfer_group_id], other_user.id
        )

        assert counterparts == {}
