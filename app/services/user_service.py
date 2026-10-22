import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import assert_never
from uuid import UUID, uuid4

import structlog

from app.core import UnitOfWork, settings, utc_now
from app.core.error_codes import ErrorCode
from app.core.exceptions import AuthenticationException, ValueExistsException
from app.core.security import (
    Argon2Hasher,
    create_access_token,
    create_refresh_token,
    derive_refresh_secret,
    fingerprint_email,
    hash_refresh_secret,
    parse_refresh_token,
    verify_refresh_token_signature,
)
from app.models import (
    INITIAL_REFRESH_GENERATION,
    USER_AGENT_MAX_LENGTH,
    Category,
    SessionRevocationReason,
    User,
    UserSession,
)
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

INVALID_CREDENTIALS_MESSAGE = "Invalid email or password"


class RefreshTokenMatch(StrEnum):
    CURRENT = "current"
    PREVIOUS_IN_GRACE = "previous_in_grace"
    MISMATCH = "mismatch"


@dataclass(frozen=True)
class ResolvedRefreshToken:
    user_session: UserSession
    match: RefreshTokenMatch
    now: datetime


class UserService:
    def __init__(
        self,
        user_repository: UserRepository,
        user_session_repository: UserSessionRepository,
        unit_of_work: UnitOfWork,
        category_repository: CategoryRepository,
        *,
        password_hasher: Argon2Hasher,
    ):
        self.user_repository = user_repository
        self.user_session_repository = user_session_repository
        self.unit_of_work = unit_of_work
        self.category_repository = category_repository
        self.password_hasher = password_hasher

    async def register_user(self, user: UserCreate) -> UserResponse:
        if await self.user_repository.get_by_email(user.email):
            raise ValueExistsException("User with this email already exists", loc=("email",))

        if await self.user_repository.get_by_username(user.username):
            raise ValueExistsException("User with this username already exists", loc=("username",))

        # Release the read transaction's connection before waiting for Argon2.
        await self.unit_of_work.commit()

        new_user = User(
            username=user.username,
            email=user.email,
            hashed_password=await self.password_hasher.hash(user.password),
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

    def _set_refresh_secret(self, user_session: UserSession) -> str:
        """Derive the secret of the session's current generation and store its hash."""
        secret = derive_refresh_secret(user_session.id, user_session.refresh_generation)
        user_session.refresh_token_hash = hash_refresh_secret(secret)

        return secret

    def _replayable_secret(self, user_session: UserSession) -> str | None:
        """Secret of the current generation, if that is the one the stored hash belongs to.

        A session whose current secret was issued at random, before secrets were derived,
        cannot hand it out again: only its hash is known.
        """
        secret = derive_refresh_secret(user_session.id, user_session.refresh_generation)
        if not hmac.compare_digest(hash_refresh_secret(secret), user_session.refresh_token_hash):
            return None

        return secret

    def _issue_tokens(self, user_session: UserSession, secret: str) -> TokenResponse:
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

        return TokenResponse(
            access_token=create_access_token(
                {"sub": str(user_session.user_id), "sid": str(user_session.id)},
                expires_delta=timedelta(seconds=expires_in),
            ),
            refresh_token=create_refresh_token(user_session.id, secret),
            expires_in=expires_in,
        )

    async def _resolve_refresh_token(self, token: str) -> ResolvedRefreshToken | None:
        parsed_token = parse_refresh_token(token)
        if parsed_token is None:
            logger.warning("refresh_token_rejected_malformed")
            return None

        session_id, secret, signature = parsed_token
        if not verify_refresh_token_signature(session_id, secret, signature):
            logger.warning("refresh_token_rejected_invalid_signature", session_id=str(session_id))
            return None

        user_session = await self.user_session_repository.get_by_id_for_update(session_id)
        if user_session is None:
            logger.warning("refresh_token_rejected_session_not_found", session_id=str(session_id))
            return None

        now = utc_now()

        if user_session.revoked_at is not None:
            logger.warning(
                "refresh_token_used_on_revoked_session",
                session_id=str(session_id),
                revoked_reason=user_session.revoked_reason,
            )
            return None

        if user_session.expires_at <= now:
            logger.info("refresh_token_rejected_session_expired", session_id=str(session_id))
            return None

        secret_hash = hash_refresh_secret(secret)
        if hmac.compare_digest(secret_hash, user_session.refresh_token_hash):
            return ResolvedRefreshToken(
                user_session=user_session, match=RefreshTokenMatch.CURRENT, now=now
            )

        if (
            user_session.previous_refresh_token_hash is not None
            and user_session.rotated_at is not None
            and hmac.compare_digest(secret_hash, user_session.previous_refresh_token_hash)
            and now - user_session.rotated_at
            <= timedelta(seconds=settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS)
        ):
            return ResolvedRefreshToken(
                user_session=user_session, match=RefreshTokenMatch.PREVIOUS_IN_GRACE, now=now
            )

        return ResolvedRefreshToken(
            user_session=user_session, match=RefreshTokenMatch.MISMATCH, now=now
        )

    async def authenticate(self, user: UserLogin, *, user_agent: str | None) -> TokenResponse:
        existing_user = await self.user_repository.get_by_email(user.email)
        # Kept apart from existing_user: the locked re-read below uses populate_existing
        # and overwrites that object in place.
        verified_hash = existing_user.hashed_password if existing_user else None

        # Release the read transaction's connection before waiting for Argon2.
        await self.unit_of_work.commit()

        if verified_hash is not None:
            is_password_valid = await self.password_hasher.verify(user.password, verified_hash)
        else:
            is_password_valid = await self.password_hasher.verify_dummy(user.password)

        if not existing_user or not is_password_valid:
            log_fields = (
                {"user_id": existing_user.id}
                if existing_user
                else {"email_fingerprint": fingerprint_email(user.email)}
            )
            logger.warning("user_authenticate_failed", **log_fields)

            raise AuthenticationException(
                INVALID_CREDENTIALS_MESSAGE, code=ErrorCode.INVALID_CREDENTIALS
            )

        # The password is verified without a lock so the slow hash check does not hold
        # the user row.
        # The re-read takes the lock to serialize login with password changes: if the
        # hash changed after verification, the password used here is no longer valid.
        locked_user = await self.user_repository.get_by_id_for_update(existing_user.id)

        if locked_user is None:
            logger.warning(
                "user_authenticate_rejected_user_deleted",
                user_id=existing_user.id,
            )

            raise AuthenticationException(
                INVALID_CREDENTIALS_MESSAGE, code=ErrorCode.INVALID_CREDENTIALS
            )

        if locked_user.hashed_password != verified_hash:
            logger.warning(
                "user_authenticate_rejected_password_changed",
                user_id=existing_user.id,
            )

            raise AuthenticationException(
                INVALID_CREDENTIALS_MESSAGE, code=ErrorCode.INVALID_CREDENTIALS
            )

        now = utc_now()

        await self.user_session_repository.delete_expired_sessions(existing_user.id, now)

        user_session = UserSession(
            id=uuid4(),
            user_id=existing_user.id,
            user_agent=user_agent[:USER_AGENT_MAX_LENGTH] if user_agent is not None else None,
            refresh_generation=INITIAL_REFRESH_GENERATION,
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=settings.SESSION_IDLE_DAYS),
        )
        secret = self._set_refresh_secret(user_session)
        tokens = self._issue_tokens(user_session, secret)

        await self.user_session_repository.add(user_session)

        await self.unit_of_work.commit()

        logger.info(
            "user_authenticate_success",
            user_id=existing_user.id,
            session_id=str(user_session.id),
        )

        return tokens

    async def refresh_session(self, refresh_token: str) -> TokenResponse:
        resolved = await self._resolve_refresh_token(refresh_token)
        if resolved is None:
            raise AuthenticationException("Invalid or expired token")

        user_session = resolved.user_session
        match = resolved.match
        now = resolved.now
        if match is RefreshTokenMatch.MISMATCH:
            user_session.revoked_at = now
            user_session.revoked_reason = SessionRevocationReason.REUSE_DETECTED
            await self.user_session_repository.update(user_session)
            await self.unit_of_work.commit()

            logger.warning(
                "refresh_token_reuse_detected",
                session_id=str(user_session.id),
                user_id=user_session.user_id,
            )
            raise AuthenticationException("Invalid or expired token")

        if match is RefreshTokenMatch.CURRENT:
            user_session.previous_refresh_token_hash = user_session.refresh_token_hash
            user_session.rotated_at = now
            user_session.refresh_generation += 1
            secret = self._set_refresh_secret(user_session)
        elif match is RefreshTokenMatch.PREVIOUS_IN_GRACE:
            # A replay inside the grace window gets the successor the first refresh issued, so
            # nothing is rotated. It is checked before the session is touched, because a
            # replay that cannot be served must leave the session as it was.
            replayed_secret = self._replayable_secret(user_session)
            if replayed_secret is None:
                logger.warning("refresh_replay_unavailable", session_id=str(user_session.id))
                raise AuthenticationException("Invalid or expired token")
            secret = replayed_secret
        else:
            assert_never(match)

        user_session.last_used_at = now
        user_session.expires_at = min(
            now + timedelta(days=settings.SESSION_IDLE_DAYS),
            user_session.created_at + timedelta(days=settings.SESSION_MAX_DAYS),
        )
        tokens = self._issue_tokens(user_session, secret)

        await self.user_session_repository.update(user_session)
        await self.unit_of_work.commit()

        logger.info(
            "user_session_refresh_success", session_id=str(user_session.id), match=match.value
        )

        return tokens

    async def logout(self, refresh_token: str) -> None:
        resolved = await self._resolve_refresh_token(refresh_token)
        if resolved is None:
            return

        user_session = resolved.user_session
        match = resolved.match
        now = resolved.now
        if match is RefreshTokenMatch.MISMATCH:
            logger.warning("logout_ignored_stale_refresh_token", session_id=str(user_session.id))
            return

        user_session.revoked_at = now
        user_session.revoked_reason = SessionRevocationReason.LOGOUT

        await self.user_session_repository.update(user_session)
        await self.unit_of_work.commit()

        logger.info("user_logout_success", session_id=str(user_session.id), match=match.value)

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

    async def update_password(
        self, data: PasswordUpdate, user_id: int, *, current_session_id: UUID
    ) -> None:
        # Lock the user before checking the password to serialize password changes
        # with logins and other password changes.
        existing_user = await validators.validate_user_for_update(self.user_repository, user_id)

        if not await self.password_hasher.verify(
            data.current_password, existing_user.hashed_password
        ):
            logger.warning("password_update_failed", user_id=user_id)

            raise AuthenticationException(
                "Current password is incorrect",
                code=ErrorCode.INVALID_CREDENTIALS,
                loc=("current_password",),
            )

        existing_user.hashed_password = await self.password_hasher.hash(data.new_password)
        now = utc_now()
        existing_user.password_changed_at = now

        await self.user_repository.update(existing_user)
        revoked_count = await self.user_session_repository.revoke_active_except(
            user_id,
            keep_session_id=current_session_id,
            now=now,
            reason=SessionRevocationReason.PASSWORD_CHANGED,
        )

        await self.unit_of_work.commit()

        logger.info(
            "password_update_success", user_id=existing_user.id, revoked_count=revoked_count
        )
