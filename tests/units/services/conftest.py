import pytest
from pytest_mock import MockerFixture

import datetime
from decimal import Decimal

from app.services import TransactionService, CategoryService, CurrencyService, UserService, TransactionTemplateService
from app.repositories import TransactionRepository, CurrencyRepository, CategoryRepository, UserRepository, \
    TransactionTemplateRepository
from app.models import Transaction, TransactionType, Currency, Category, User, TransactionTemplate


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
def transaction_template_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=TransactionTemplateRepository)


@pytest.fixture
def user_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=UserRepository)


@pytest.fixture
def transaction_service(
        transaction_repo_mock: TransactionRepository,
        currency_repo_mock: CurrencyRepository,
        transaction_template_repo_mock: TransactionTemplateRepository,
        category_repo_mock: CategoryRepository
):
    return TransactionService(
        transaction_repository=transaction_repo_mock,
        transaction_template_repository=transaction_template_repo_mock,
        category_repository=category_repo_mock,
        currency_repository=currency_repo_mock,
    )


@pytest.fixture
def transaction_template_service(
        transaction_template_repo_mock: TransactionTemplateRepository,
        category_repo_mock: CategoryRepository,
        currency_repo_mock: CurrencyRepository,
):
    return TransactionTemplateService(
        transaction_template_repository=transaction_template_repo_mock,
        category_repository=category_repo_mock,
        currency_repository=currency_repo_mock,
    )


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
def existing_transaction(
        existing_user: User,
        existing_currency: Currency,
):
    return Transaction(
        id=1,
        type=TransactionType.INCOME,
        amount=Decimal("5000.00"),
        currency_code=existing_currency.code,
        description="Salary",
        date=datetime.date(2026, 2, 10),
        user_id=existing_user.id,
    )


@pytest.fixture
def existing_category(
        existing_user: User,
):
    return Category(
        id=1,
        name="Foods",
        user_id=existing_user.id,
        created_at=datetime.datetime(2026, 2, 10),
        archived_at=None
    )


@pytest.fixture
def existing_currency():
    return Currency(
        code="UAH",
        symbol="₴",
        name="Ukrainian Hryvnia",
        is_active=True
    )


@pytest.fixture
def existing_template(
        existing_user: User,
        existing_category: Category
):
    return TransactionTemplate(
        id=1,
        name="Morning Coffee",
        type=TransactionType.EXPENSE,
        amount=Decimal("50.00"),
        description="Daily coffee expense",
        currency_code="UAH",
        user_id=existing_user.id,
        created_at=datetime.datetime(2026, 2, 10)
    )


@pytest.fixture
def plain_existing_user_password():
    return "Password1234"


@pytest.fixture
def existing_user():
    return User(
        id=1,
        email="user@test.com",
        username="user",
        hashed_password="hashed_password",
        created_at=datetime.datetime(2026, 2, 10),
    )
