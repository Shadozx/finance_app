from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import UnitOfWork, get_session, verify_token
from app.core.exceptions import AuthenticationException
from app.models import User
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
    StatisticsService,
    TransactionService,
    TransactionTemplateService,
    TransferService,
    UserService,
)


def get_user_service(
    session: AsyncSession = Depends(get_session),
) -> UserService:
    user_repository = UserRepository(session)
    unit_of_work = UnitOfWork(session)

    return UserService(user_repository=user_repository, unit_of_work=unit_of_work)


def get_category_service(
    session: AsyncSession = Depends(get_session),
) -> CategoryService:
    category_repository = CategoryRepository(session)
    unit_of_work = UnitOfWork(session)

    return CategoryService(category_repository=category_repository, unit_of_work=unit_of_work)


def get_transaction_service(
    session: AsyncSession = Depends(get_session),
) -> TransactionService:
    category_repository = CategoryRepository(session)
    currency_repository = CurrencyRepository(session)
    transaction_repository = TransactionRepository(session)
    transaction_split_repository = TransactionSplitRepository(session)
    transaction_template_repository = TransactionTemplateRepository(session)
    account_repository = AccountRepository(session)
    unit_of_work = UnitOfWork(session)

    return TransactionService(
        transaction_repository=transaction_repository,
        transaction_split_repository=transaction_split_repository,
        transaction_template_repository=transaction_template_repository,
        category_repository=category_repository,
        currency_repository=currency_repository,
        account_repository=account_repository,
        unit_of_work=unit_of_work,
    )


def get_transaction_template_service(
    session: AsyncSession = Depends(get_session),
) -> TransactionTemplateService:
    category_repository = CategoryRepository(session)
    currency_repository = CurrencyRepository(session)
    transaction_template_repository = TransactionTemplateRepository(session)
    unit_of_work = UnitOfWork(session)

    return TransactionTemplateService(
        transaction_template_repository=transaction_template_repository,
        category_repository=category_repository,
        currency_repository=currency_repository,
        unit_of_work=unit_of_work,
    )


def get_statistics_service(session: AsyncSession = Depends(get_session)) -> StatisticsService:
    transaction_repository = TransactionRepository(session)

    return StatisticsService(transaction_repository)


def get_currency_service(session: AsyncSession = Depends(get_session)) -> CurrencyService:
    currency_repository = CurrencyRepository(session)

    return CurrencyService(currency_repository)


def get_budget_service(
    session: AsyncSession = Depends(get_session),
) -> BudgetService:
    budget_repository = BudgetRepository(session)
    transaction_repository = TransactionRepository(session)
    category_repository = CategoryRepository(session)
    currency_repository = CurrencyRepository(session)
    unit_of_work = UnitOfWork(session)

    return BudgetService(
        budget_repository=budget_repository,
        transaction_repository=transaction_repository,
        category_repository=category_repository,
        currency_repository=currency_repository,
        unit_of_work=unit_of_work,
    )


def get_account_service(
    session: AsyncSession = Depends(get_session),
) -> AccountService:
    account_repository = AccountRepository(session)
    currency_repository = CurrencyRepository(session)
    transaction_repository = TransactionRepository(session)
    unit_of_work = UnitOfWork(session)

    return AccountService(
        account_repository=account_repository,
        currency_repository=currency_repository,
        transaction_repository=transaction_repository,
        unit_of_work=unit_of_work,
    )


def get_transfer_service(
    session: AsyncSession = Depends(get_session),
) -> TransferService:
    transaction_repository = TransactionRepository(session)
    account_repository = AccountRepository(session)
    currency_repository = CurrencyRepository(session)
    unit_of_work = UnitOfWork(session)

    return TransferService(
        transaction_repository=transaction_repository,
        account_repository=account_repository,
        currency_repository=currency_repository,
        unit_of_work=unit_of_work,
    )


security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not credentials:
        raise AuthenticationException("Authorization header missing")

    try:
        payload = verify_token(credentials.credentials)
    except ValueError as err:
        raise AuthenticationException("Invalid or expired token") from err

    user_id = int(payload["sub"])

    user_repository = UserRepository(session)

    user = await user_repository.get_by_id(user_id)

    if not user:
        raise AuthenticationException("User no longer exists")

    return user
