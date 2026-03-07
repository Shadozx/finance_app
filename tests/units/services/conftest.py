import pytest
from pytest_mock import MockerFixture

import datetime
from decimal import Decimal

from app.services import TransactionService, CategoryService, CurrencyService, UserService
from app.repositories import TransactionRepository, CurrencyRepository, CategoryRepository, UserRepository
from app.models import Transaction, TransactionType, Currency, Category, User
from app.core import hash_password


@pytest.fixture
def category_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=CategoryRepository)


@pytest.fixture
def currency_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=CurrencyRepository)


@pytest.fixture
def transaction_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=TransactionRepository)


@pytest.fixture
def user_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=UserRepository)


@pytest.fixture
def transaction_service(transaction_repo_mock: TransactionRepository, currency_repo_mock: CurrencyRepository,
                        category_repo_mock: CategoryRepository):
    return TransactionService(transaction_repo_mock, category_repo_mock, currency_repo_mock)


@pytest.fixture
def category_service(category_repo_mock: CategoryRepository):
    return CategoryService(category_repo_mock)


@pytest.fixture
def currency_service(currency_repo_mock: CurrencyRepository):
    return CurrencyService(currency_repo_mock)


@pytest.fixture
def user_service(user_repo_mock: UserRepository):
    return UserService(user_repo_mock)


@pytest.fixture
def existing_transaction():
    return Transaction(
        id=1,
        type=TransactionType.INCOME,
        amount=Decimal("5000.00"),
        currency_code="UAH",
        description="Salary",
        date=datetime.date(2026, 2, 10),
        user_id=1
    )


@pytest.fixture
def existing_category():
    return Category(
        id=1,
        name="Foods",
        user_id=1,
        created_at=datetime.datetime(2026, 2, 10),
        archived_at=None
    )


@pytest.fixture
def existing_currency():
    return Currency(
        code="UAH", symbol="₴", name="Ukrainian Hryvnia", is_active=True
    )


@pytest.fixture
def plain_existing_user_password():
    return "Password1234"


@pytest.fixture
def existing_user(plain_existing_user_password: str):
    return User(
        id=1,
        email="user@test.com",
        username="user",
        hashed_password=hash_password(plain_existing_user_password),
        created_at=datetime.datetime(2026, 2, 10),
    )
