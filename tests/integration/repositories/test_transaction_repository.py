from decimal import Decimal
from datetime import date
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import UserRepository, TransactionRepository
from app.models import User, Transaction, TransactionType, Category, Currency
from app.schemas import TransactionFilters


@pytest.fixture
def transaction_repository(
        test_session: AsyncSession,
):
    return TransactionRepository(test_session)


@pytest.fixture
async def transaction(
        transaction_repository: TransactionRepository,
        user: User,
        category: Category,
        uah_currency: Currency,
):
    return await transaction_repository.create(Transaction(
        type=TransactionType.EXPENSE,
        description="Morning Coffee",
        amount=Decimal("100.00"),
        currency_code=uah_currency.code,
        category_id=category.id,
        user_id=user.id,
        date=date(2025, 3, 1)
    ))


class TestCreate:

    async def test_create(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            category: Category,
            uah_currency: Currency,
    ):
        transaction = Transaction(
            type=TransactionType.EXPENSE,
            description="Morning Coffee",
            amount=Decimal("100.00"),
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=user.id,
            date=date(2025, 3, 1)
        )

        created_transaction = await transaction_repository.create(transaction)

        assert created_transaction.id is not None

        assert created_transaction.type == transaction.type
        assert created_transaction.description == transaction.description
        assert created_transaction.amount == transaction.amount
        assert created_transaction.currency_code == transaction.currency_code
        assert created_transaction.category_id == transaction.category_id
        assert created_transaction.user_id == transaction.user_id
        assert created_transaction.date == transaction.date


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
            transaction: Transaction,
            uah_currency: Currency,
    ):
        await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE,
            description="Foods",
            amount=Decimal("550.00"),
            currency_code=uah_currency.code,
            user_id=user.id,
            date=date(2025, 3, 3)
        ))

        await transaction_repository.create(Transaction(
            type=TransactionType.INCOME,
            amount=Decimal("35000.00"),
            description="Salary",
            currency_code=uah_currency.code,
            user_id=user.id,
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
            user: User,
            transaction: Transaction,
            usd_currency: Currency,
    ):
        other_user_repository = UserRepository(test_session)
        other_user = await other_user_repository.create(User(
            email="other@test.com",
            username="other",
            hashed_password="hashed",
        ))

        await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE,
            amount=Decimal("50.00"),
            description="Netflix",
            currency_code=usd_currency.code,
            user_id=other_user.id,
            date=date(2026, 2, 15),
        ))

        transactions = await transaction_repository.get_by_user(user.id, TransactionFilters())

        assert len(transactions) == 1

        assert transactions[0].id == transaction.id
        assert transactions[0].description == transaction.description
        assert transactions[0].user_id == transaction.user_id

    async def test_get_by_user_ordered_by_date_desc(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            uah_currency: Currency,
    ):
        t_old = await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE,
            amount=Decimal("100.00"),
            description="Old",
            currency_code=uah_currency.code,
            user_id=user.id,
            date=date(2026, 1, 1),
        ))

        t_new = await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE,
            amount=Decimal("200.00"),
            description="New",
            currency_code=uah_currency.code,
            user_id=user.id,
            date=date(2026, 3, 1),
        ))

        t_mid = await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE,
            amount=Decimal("150.00"),
            description="Mid",
            currency_code=uah_currency.code,
            user_id=user.id,
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
        uah_currency: Currency,
        usd_currency: Currency,
        category: Category
):
    t1 = await transaction_repository.create(Transaction(
        type=TransactionType.INCOME,
        amount=Decimal("10000.00"),
        description="Salary",
        currency_code=usd_currency.code,
        user_id=user.id,
        category_id=category.id,
        date=date(2026, 1, 15),
    ))

    t2 = await transaction_repository.create(Transaction(
        type=TransactionType.EXPENSE,
        amount=Decimal("150.00"),
        description="Coffee",
        currency_code=uah_currency.code,
        user_id=user.id,
        category_id=category.id,
        date=date(2026, 2, 10),
    ))

    t3 = await transaction_repository.create(Transaction(
        type=TransactionType.EXPENSE,
        amount=Decimal("50.00"),
        description="Netflix",
        currency_code=usd_currency.code,
        user_id=user.id,
        category_id=None,
        date=date(2026, 2, 15),
    ))

    t4 = await transaction_repository.create(Transaction(
        type=TransactionType.INCOME,
        amount=Decimal("500.00"),
        description="Freelance",
        currency_code=usd_currency.code,
        user_id=user.id,
        category_id=None,
        date=date(2026, 3, 1),
    ))

    t5 = await transaction_repository.create(Transaction(
        type=TransactionType.EXPENSE,
        amount=Decimal("200.00"),
        description="Lunch",
        currency_code=uah_currency.code,
        user_id=user.id,
        category_id=category.id,
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
        transaction.amount = Decimal("155.00")

        updated_transaction = await transaction_repository.update(transaction)

        assert updated_transaction.id == transaction.id
        assert updated_transaction.amount == transaction.amount

        found_transaction = await transaction_repository.get_by_id(transaction.id)
        assert found_transaction.amount == transaction.amount


class TestDelete:
    async def test_delete(
            self,
            transaction_repository: TransactionRepository,
            transaction: Transaction
    ):
        await transaction_repository.delete(transaction)

        found_transaction = await transaction_repository.get_by_id(transaction.id)
        assert found_transaction is None
