import datetime
from decimal import Decimal

import pytest
from pytest_mock import MockerFixture

from app.core import UnitOfWork
from app.models import (
    Account,
    Category,
    Currency,
    TransactionKind,
    TransactionType,
    User,
)
from app.repositories import (
    AccountRepository,
    BudgetRepository,
    CategoryRepository,
    CurrencyRepository,
    TransactionRepository,
    TransactionSplitRepository,
    TransactionTemplateRepository,
    UserRepository,
)
from app.services import (
    AccountService,
    BudgetService,
    CategoryService,
    CurrencyService,
    TransactionService,
    TransactionTemplateService,
    TransferService,
    UserService,
)
from tests.units.services.helpers import (
    make_account,
    make_budget,
    make_category,
    make_transaction,
    make_transaction_template,
    make_user,
)


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
def transaction_split_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=TransactionSplitRepository)


@pytest.fixture
def transaction_template_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=TransactionTemplateRepository)


@pytest.fixture
def user_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=UserRepository)


@pytest.fixture
def budget_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=BudgetRepository)


@pytest.fixture
def account_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=AccountRepository)


@pytest.fixture
def unit_of_work_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=UnitOfWork)


@pytest.fixture
def transaction_service(
    transaction_repo_mock: TransactionRepository,
    transaction_split_repo_mock: TransactionSplitRepository,
    transaction_template_repo_mock: TransactionTemplateRepository,
    currency_repo_mock: CurrencyRepository,
    category_repo_mock: CategoryRepository,
    account_repo_mock: AccountRepository,
    unit_of_work_mock: UnitOfWork,
):
    return TransactionService(
        transaction_repository=transaction_repo_mock,
        transaction_split_repository=transaction_split_repo_mock,
        transaction_template_repository=transaction_template_repo_mock,
        category_repository=category_repo_mock,
        currency_repository=currency_repo_mock,
        account_repository=account_repo_mock,
        unit_of_work=unit_of_work_mock,
    )


@pytest.fixture
def transaction_template_service(
    transaction_template_repo_mock: TransactionTemplateRepository,
    category_repo_mock: CategoryRepository,
    currency_repo_mock: CurrencyRepository,
    unit_of_work_mock: UnitOfWork,
):
    return TransactionTemplateService(
        transaction_template_repository=transaction_template_repo_mock,
        category_repository=category_repo_mock,
        currency_repository=currency_repo_mock,
        unit_of_work=unit_of_work_mock,
    )


@pytest.fixture
def category_service(category_repo_mock: CategoryRepository, unit_of_work_mock: UnitOfWork):
    return CategoryService(category_repository=category_repo_mock, unit_of_work=unit_of_work_mock)


@pytest.fixture
def currency_service(currency_repo_mock: CurrencyRepository):
    return CurrencyService(currency_repo_mock)


@pytest.fixture
def user_service(user_repo_mock: UserRepository, unit_of_work_mock: UnitOfWork):
    return UserService(user_repository=user_repo_mock, unit_of_work=unit_of_work_mock)


@pytest.fixture
def budget_service(
    budget_repo_mock: BudgetRepository,
    category_repo_mock: CategoryRepository,
    currency_repo_mock: CurrencyRepository,
    transaction_repo_mock: TransactionRepository,
    unit_of_work_mock: UnitOfWork,
):
    return BudgetService(
        budget_repository=budget_repo_mock,
        category_repository=category_repo_mock,
        currency_repository=currency_repo_mock,
        transaction_repository=transaction_repo_mock,
        unit_of_work=unit_of_work_mock,
    )


@pytest.fixture
def account_service(
    account_repo_mock: AccountRepository,
    currency_repo_mock: CurrencyRepository,
    transaction_repo_mock: TransactionRepository,
    unit_of_work_mock: UnitOfWork,
):
    return AccountService(
        account_repository=account_repo_mock,
        currency_repository=currency_repo_mock,
        transaction_repository=transaction_repo_mock,
        unit_of_work=unit_of_work_mock,
    )


@pytest.fixture
def transfer_service(
    transaction_repo_mock: TransactionRepository,
    account_repo_mock: AccountRepository,
    currency_repo_mock: CurrencyRepository,
    unit_of_work_mock: UnitOfWork,
):
    return TransferService(
        transaction_repository=transaction_repo_mock,
        account_repository=account_repo_mock,
        currency_repository=currency_repo_mock,
        unit_of_work=unit_of_work_mock,
    )


@pytest.fixture
def existing_transaction(
    existing_user: User,
    existing_currency: Currency,
    existing_account: Account,
):
    return make_transaction(
        id=1,
        type=TransactionType.INCOME,
        kind=TransactionKind.REGULAR,
        amount=Decimal("5000.00"),
        currency_code=existing_currency.code,
        description="Salary",
        date=datetime.date(2026, 2, 10),
        user_id=existing_user.id,
        account_id=existing_account.id,
    )


@pytest.fixture
def existing_category(
    existing_user: User,
):
    return make_category(
        id=1,
        name="Foods",
        user_id=existing_user.id,
        created_at=datetime.datetime(2026, 2, 10),
        archived_at=None,
    )


@pytest.fixture
def existing_currency():
    return Currency(code="UAH", symbol="₴", name="Ukrainian Hryvnia", is_active=True)


@pytest.fixture
def existing_usd_currency():
    return Currency(code="USD", symbol="$", name="US Dollar", is_active=True)


@pytest.fixture
def existing_template(
    existing_user: User,
):
    return make_transaction_template(
        id=1,
        name="Morning Coffee",
        amount=Decimal("50.00"),
        currency_code="UAH",
        description="Daily coffee expense",
        user_id=existing_user.id,
    )


@pytest.fixture
def plain_existing_user_password():
    return "Password1234"


@pytest.fixture
def existing_user():
    return make_user(
        id=1,
        email="user@test.com",
        username="user",
    )


@pytest.fixture
def existing_budget(
    existing_user: User,
    existing_currency: Currency,
    existing_category: Category,
):
    return make_budget(
        id=1,
        name="Food budget",
        amount=Decimal("5000.00"),
        currency_code=existing_currency.code,
        category_id=existing_category.id,
        start_date=datetime.date(2026, 7, 1),
        end_date=datetime.date(2026, 7, 31),
        user_id=existing_user.id,
    )


@pytest.fixture
def zero_budget(
    existing_user: User,
    existing_currency: Currency,
    existing_category: Category,
):
    return make_budget(
        id=2,
        name="Zero budget",
        amount=Decimal("0"),
        currency_code=existing_currency.code,
        category_id=existing_category.id,
        start_date=datetime.date(2026, 7, 1),
        end_date=datetime.date(2026, 7, 31),
        user_id=existing_user.id,
    )


@pytest.fixture
def existing_account(
    existing_user: User,
    existing_currency: Currency,
):
    return make_account(
        id=1,
        name="Monobank",
        currency_code=existing_currency.code,
        user_id=existing_user.id,
        created_at=datetime.datetime(2026, 2, 10),
    )


@pytest.fixture
def existing_usd_account(
    existing_user: User,
    existing_usd_currency: Currency,
):
    return make_account(
        id=2,
        name="Dollars",
        currency_code=existing_usd_currency.code,
        user_id=existing_user.id,
        created_at=datetime.datetime(2026, 2, 10),
    )
