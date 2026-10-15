import datetime
import uuid
from decimal import Decimal

import pytest
from pytest_mock import MockerFixture

from app.core import UnitOfWork, settings
from app.core.security import Argon2Hasher, hash_refresh_secret
from app.models import (
    Account,
    Category,
    Currency,
    TransactionKind,
    TransactionType,
    User,
    UserSession,
)
from app.repositories import (
    AccountRepository,
    BudgetRepository,
    CategoryRepository,
    CurrencyRepository,
    TransactionRepository,
    TransactionSplitRepository,
    TransactionTemplateRepository,
    TransactionTemplateSplitRepository,
    UserRepository,
    UserSessionRepository,
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
    UserSessionService,
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
def transaction_template_split_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=TransactionTemplateSplitRepository)


@pytest.fixture
def user_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=UserRepository)


@pytest.fixture
def user_session_repo_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=UserSessionRepository)


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
    currency_repo_mock: CurrencyRepository,
    category_repo_mock: CategoryRepository,
    account_repo_mock: AccountRepository,
    unit_of_work_mock: UnitOfWork,
):
    return TransactionService(
        transaction_repository=transaction_repo_mock,
        transaction_split_repository=transaction_split_repo_mock,
        category_repository=category_repo_mock,
        currency_repository=currency_repo_mock,
        account_repository=account_repo_mock,
        unit_of_work=unit_of_work_mock,
    )


@pytest.fixture
def transaction_template_service(
    transaction_template_repo_mock: TransactionTemplateRepository,
    transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
    category_repo_mock: CategoryRepository,
    currency_repo_mock: CurrencyRepository,
    unit_of_work_mock: UnitOfWork,
):
    return TransactionTemplateService(
        transaction_template_repository=transaction_template_repo_mock,
        transaction_template_split_repository=transaction_template_split_repo_mock,
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
def password_hasher_mock(mocker: MockerFixture):
    return mocker.AsyncMock(spec=Argon2Hasher)


@pytest.fixture
def user_service(
    user_repo_mock: UserRepository,
    unit_of_work_mock: UnitOfWork,
    category_repo_mock: CategoryRepository,
    user_session_repo_mock: UserSessionRepository,
    password_hasher_mock: Argon2Hasher,
):
    return UserService(
        user_repository=user_repo_mock,
        unit_of_work=unit_of_work_mock,
        category_repository=category_repo_mock,
        user_session_repository=user_session_repo_mock,
        password_hasher=password_hasher_mock,
    )


@pytest.fixture
def user_session_service(
    user_session_repo_mock: UserSessionRepository,
    unit_of_work_mock: UnitOfWork,
):
    return UserSessionService(
        user_session_repository=user_session_repo_mock,
        unit_of_work=unit_of_work_mock,
    )


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
        created_at=datetime.datetime(2026, 2, 10, tzinfo=datetime.UTC),
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
def refresh_secret():
    return "original-refresh-secret"


@pytest.fixture
def session_now(mocker: MockerFixture):
    now = datetime.datetime.now(datetime.UTC)
    mocker.patch("app.services.user_service.utc_now", return_value=now)
    mocker.patch("app.services.user_session_service.utc_now", return_value=now)
    return now


@pytest.fixture
def active_user_session(existing_user: User, refresh_secret: str, session_now: datetime.datetime):
    session_age = datetime.timedelta(days=1)
    return UserSession(
        id=uuid.uuid4(),
        user_id=existing_user.id,
        refresh_token_hash=hash_refresh_secret(refresh_secret),
        created_at=session_now - session_age,
        last_used_at=session_now - session_age,
        expires_at=session_now + datetime.timedelta(days=settings.SESSION_IDLE_DAYS) - session_age,
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
        created_at=datetime.datetime(2026, 2, 10, tzinfo=datetime.UTC),
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
        created_at=datetime.datetime(2026, 2, 10, tzinfo=datetime.UTC),
    )
