import hmac
from datetime import timedelta
from uuid import uuid4

import structlog

from app.core import UnitOfWork, settings, utc_now
from app.core.error_codes import ErrorCode
from app.core.exceptions import AuthenticationException, ValueExistsException
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_refresh_token,
    generate_refresh_secret,
    hash_password,
    hash_refresh_secret,
    parse_refresh_token,
    verify_password,
)
from app.models import USER_AGENT_MAX_LENGTH, Category, User, UserSession
from app.repositories import CategoryRepository, UserRepository, UserSessionRepository
from app.schemas import (
    PasswordUpdate,
    TokenResponse,
    UserCreate,
    UserLogin,
    UsernameUpdate,
    UserResponse,
)
from app.services import validators
from app.services.default_categories import DEFAULT_CATEGORIES

logger = structlog.get_logger()


class UserService:
    def __init__(
        self,
        user_repository: UserRepository,
        user_session_repository: UserSessionRepository,
        unit_of_work: UnitOfWork,
        category_repository: CategoryRepository,
    ):
        self.user_repository = user_repository
        self.user_session_repository = user_session_repository
        self.unit_of_work = unit_of_work
        self.category_repository = category_repository

    async def register_user(self, user: UserCreate) -> UserResponse:
        if await self.user_repository.get_by_email(user.email):
            raise ValueExistsException("User with this email already exists", loc=("email",))

        if await self.user_repository.get_by_username(user.username):
            raise ValueExistsException("User with this username already exists", loc=("username",))

        new_user = User(
            username=user.username, email=user.email, hashed_password=hash_password(user.password)
        )

        created_user = await self.user_repository.add(new_user)

        default_categories = [
            Category(name=name, type=category_type, user_id=created_user.id)
            for name, category_type in DEFAULT_CATEGORIES
        ]
        await self.category_repository.add_all(default_categories)

        await self.unit_of_work.commit()

        logger.info("user_register_success", user_id=created_user.id)

        return UserResponse.model_validate(created_user)

    def _issue_tokens(self, user_session: UserSession) -> TokenResponse:
        secret = generate_refresh_secret()
        user_session.refresh_token_hash = hash_refresh_secret(secret)

        return TokenResponse(
            access_token=create_access_token(
                {"sub": str(user_session.user_id), "sid": str(user_session.id)}
            ),
            refresh_token=create_refresh_token(user_session.id, secret),
        )

    async def authenticate(self, user: UserLogin, *, user_agent: str | None) -> TokenResponse:
        existing_user = await self.user_repository.get_by_email(user.email)

        hashed_password = existing_user.hashed_password if existing_user else DUMMY_PASSWORD_HASH

        is_password_valid = verify_password(user.password, hashed_password)

        if not existing_user or not is_password_valid:
            logger.warning("user_authenticate_failed", email=user.email)

            raise AuthenticationException(
                "Invalid email or password", code=ErrorCode.INVALID_CREDENTIALS
            )

        now = utc_now()

        await self.user_session_repository.delete_expired_sessions(existing_user.id, now)

        user_session = UserSession(
            id=uuid4(),
            user_id=existing_user.id,
            user_agent=user_agent[:USER_AGENT_MAX_LENGTH] if user_agent is not None else None,
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=settings.SESSION_IDLE_DAYS),
        )
        tokens = self._issue_tokens(user_session)

        await self.user_session_repository.add(user_session)

        await self.unit_of_work.commit()

        logger.info(
            "user_authenticate_success",
            user_id=existing_user.id,
            email=user.email,
            session_id=user_session.id,
        )

        return tokens

    async def refresh_session(self, refresh_token: str) -> TokenResponse:
        parsed_token = parse_refresh_token(refresh_token)
        if parsed_token is None:
            raise AuthenticationException()

        session_id, secret = parsed_token
        now = utc_now()
        found = await self.user_session_repository.get_active_with_user(session_id, now)
        if found is None:
            raise AuthenticationException()

        user_session, _ = found
        if not hmac.compare_digest(hash_refresh_secret(secret), user_session.refresh_token_hash):
            raise AuthenticationException()

        user_session.last_used_at = now
        user_session.expires_at = min(
            now + timedelta(days=settings.SESSION_IDLE_DAYS),
            user_session.created_at + timedelta(days=settings.SESSION_MAX_DAYS),
        )
        tokens = self._issue_tokens(user_session)

        await self.user_session_repository.update(user_session)
        await self.unit_of_work.commit()

        logger.info("user_session_refresh_success", session_id=session_id)

        return tokens

    async def logout(self, refresh_token: str) -> None:
        parsed_token = parse_refresh_token(refresh_token)
        if parsed_token is None:
            return

        session_id, secret = parsed_token
        now = utc_now()
        found = await self.user_session_repository.get_active_with_user(session_id, now)
        if found is None:
            return

        user_session, _ = found
        if not hmac.compare_digest(hash_refresh_secret(secret), user_session.refresh_token_hash):
            return

        user_session.revoked_at = now

        await self.user_session_repository.update(user_session)
        await self.unit_of_work.commit()

        logger.info("user_logout_success", session_id=session_id)

    async def update_username(self, data: UsernameUpdate, user_id: int) -> UserResponse:
        existing_user = await validators.validate_user(self.user_repository, user_id)

        duplicate_username_user = await self.user_repository.get_by_username(data.new_username)

        if duplicate_username_user and duplicate_username_user.id != user_id:
            logger.info("username_update_failed", user_id=user_id, new_username=data.new_username)

            raise ValueExistsException("Username is already taken", loc=("new_username",))

        existing_user.username = data.new_username
        updated_user = await self.user_repository.update(existing_user)

        await self.unit_of_work.commit()

        logger.info(
            "username_update_success", user_id=updated_user.id, new_username=data.new_username
        )

        return UserResponse.model_validate(updated_user)

    async def update_password(self, data: PasswordUpdate, user_id: int) -> None:
        existing_user = await validators.validate_user(self.user_repository, user_id)

        if not verify_password(data.current_password, existing_user.hashed_password):
            logger.warning("password_update_failed", user_id=user_id)

            raise AuthenticationException(
                "Current password is incorrect",
                code=ErrorCode.INVALID_CREDENTIALS,
                loc=("current_password",),
            )

        existing_user.hashed_password = hash_password(data.new_password)
        existing_user.password_changed_at = utc_now()

        await self.user_repository.update(existing_user)

        await self.unit_of_work.commit()

        logger.info("password_update_success", user_id=existing_user.id)
