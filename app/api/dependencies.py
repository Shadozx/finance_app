import uuid
from dataclasses import dataclass

import structlog
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import UnitOfWork, get_session, utc_now, verify_token
from app.core.exceptions import AuthenticationException
from app.core.security import password_hasher
from app.models import User, UserSession
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
    StatisticsService,
    TransactionService,
    TransactionTemplateService,
    TransferService,
    UserService,
    UserSessionService,
)


def get_user_service(
    session: AsyncSession = Depends(get_session),
) -> UserService:
    user_repository = UserRepository(session)
    unit_of_work = UnitOfWork(session)
    category_repository = CategoryRepository(session)
    user_session_repository = UserSessionRepository(session)

    return UserService(
        user_repository=user_repository,
        unit_of_work=unit_of_work,
        category_repository=category_repository,
        user_session_repository=user_session_repository,
        password_hasher=password_hasher,
    )


def get_user_session_service(
    session: AsyncSession = Depends(get_session),
) -> UserSessionService:
    user_session_repository = UserSessionRepository(session)
    unit_of_work = UnitOfWork(session)

    return UserSessionService(
        user_session_repository=user_session_repository,
        unit_of_work=unit_of_work,
    )


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
    account_repository = AccountRepository(session)
    unit_of_work = UnitOfWork(session)

    return TransactionService(
        transaction_repository=transaction_repository,
        transaction_split_repository=transaction_split_repository,
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
    transaction_template_split_repository = TransactionTemplateSplitRepository(session)
    unit_of_work = UnitOfWork(session)

    return TransactionTemplateService(
        transaction_template_repository=transaction_template_repository,
        transaction_template_split_repository=transaction_template_split_repository,
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


logger = structlog.get_logger()

security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    user_session: UserSession


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> AuthContext:
    if not credentials:
        raise AuthenticationException("Authorization header missing")

    try:
        payload = verify_token(credentials.credentials)
    except ValueError as err:
        raise AuthenticationException("Invalid or expired token") from err

    sid = payload.get("sid")

    if not isinstance(sid, str):
        raise AuthenticationException("Invalid or expired token")

    try:
        session_id = uuid.UUID(sid)
    except ValueError as err:
        raise AuthenticationException("Invalid or expired token") from err

    found = await UserSessionRepository(session).get_active_with_user(session_id, utc_now())

    if found is None:
        logger.warning("token_rejected_session_inactive", session_id=str(session_id))

        raise AuthenticationException("Invalid or expired token")

    user_session, user = found

    if payload.get("sub") != str(user_session.user_id):
        logger.warning(
            "token_rejected_session_user_mismatch",
            session_id=str(session_id),
            user_id=user_session.user_id,
            token_user_id=payload.get("sub"),
        )

        raise AuthenticationException("Invalid or expired token")

    return AuthContext(user=user, user_session=user_session)


async def get_current_user(context: AuthContext = Depends(get_auth_context)) -> User:
    return context.user
