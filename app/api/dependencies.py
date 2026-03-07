from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core import get_session, verify_token
from app.core.exceptions import AuthenticationException
from app.services import UserService, CategoryService, TransactionService, CurrencyService
from app.repositories import UserRepository, CategoryRepository, TransactionRepository, CurrencyRepository
from app.models import User


def get_user_service(
        session: AsyncSession = Depends(get_session)
) -> UserService:
    user_repository = UserRepository(session)

    return UserService(user_repository)


def get_category_service(
        session: AsyncSession = Depends(get_session)
) -> CategoryService:
    category_repository = CategoryRepository(session)

    return CategoryService(category_repository)


def get_transaction_service(
        session: AsyncSession = Depends(get_session)
) -> TransactionService:
    category_repository = CategoryRepository(session)
    currency_repository = CurrencyRepository(session)
    transaction_repository = TransactionRepository(session)

    return TransactionService(
        transaction_repository=transaction_repository,
        category_repository=category_repository,
        currency_repository=currency_repository
    )


def get_currency_service(
        session: AsyncSession = Depends(get_session)
) -> CurrencyService:
    currency_repository = CurrencyRepository(session)

    return CurrencyService(currency_repository)


security = HTTPBearer(auto_error=False)


async def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
        session: AsyncSession = Depends(get_session)
) -> User:
    if not credentials:
        raise AuthenticationException("Authorization header missing")

    try:
        payload = verify_token(credentials.credentials)
    except ValueError:
        raise AuthenticationException("Invalid or expired token")

    user_id = int(payload["sub"])

    user_repository = UserRepository(session)

    user = await user_repository.get_by_id(user_id)

    if not user:
        raise AuthenticationException("User no longer exists")

    return user
