import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from pytest_mock import MockerFixture
from structlog.testing import capture_logs

from app.core import UnitOfWork, settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AuthenticationException, ValueExistsException
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_refresh_token,
    hash_refresh_secret,
    parse_refresh_token,
    verify_refresh_token_signature,
    verify_token,
)
from app.models import USER_AGENT_MAX_LENGTH, SessionRevocationReason, User, UserSession
from app.repositories import CategoryRepository, UserRepository, UserSessionRepository
from app.schemas import PasswordUpdate, UserCreate, UserLogin, UsernameUpdate, UserResponse
from app.services import UserService
from app.services.default_categories import DEFAULT_CATEGORIES
from app.services.user_service import INVALID_CREDENTIALS_MESSAGE
from app.services.validators import USER_NO_LONGER_EXISTS_MESSAGE
from tests.units.services.helpers import (
    as_persisted,
    as_persisted_all,
    assert_model_fields,
    forge_refresh_token,
    make_user,
)

SESSION_TIME_OFFSET = timedelta(days=1)


class TestRegister:
    @pytest.fixture
    def data(
        self,
        existing_user: User,
        plain_existing_user_password: str,
    ):
        return UserCreate(
            email=existing_user.email,
            username=existing_user.username,
            password=plain_existing_user_password,
        )

    async def test_register_success(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_repo_mock: UserRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        data: UserCreate,
    ):
        hashed_password = "hashed"

        mock_hash = mocker.patch(
            "app.services.user_service.hash_password", return_value=hashed_password
        )

        user_repo_mock.get_by_email.return_value = None
        user_repo_mock.get_by_username.return_value = None

        user_repo_mock.add.side_effect = as_persisted
        category_repo_mock.add_all.side_effect = as_persisted_all

        result = await user_service.register_user(data)

        created_user = user_repo_mock.add.call_args[0][0]
        created_categories = category_repo_mock.add_all.call_args[0][0]

        assert result == UserResponse.model_validate(created_user)

        assert_model_fields(
            created_user, email=data.email, username=data.username, hashed_password=hashed_password
        )

        assert [(category.name, category.type) for category in created_categories] == list(
            DEFAULT_CATEGORIES
        )
        assert all(category.user_id == created_user.id for category in created_categories)

        user_repo_mock.get_by_email.assert_called_once_with(data.email)

        user_repo_mock.get_by_username.assert_called_once_with(data.username)

        mock_hash.assert_called_once_with(data.password)

        user_repo_mock.add.assert_called_once()

        category_repo_mock.add_all.assert_awaited_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_register_existing_email(
        self,
        user_service: UserService,
        user_repo_mock: UserRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        data: UserCreate,
    ):
        user_repo_mock.get_by_email.return_value = existing_user

        with pytest.raises(ValueExistsException, match="User with this email already exists"):
            await user_service.register_user(data)

        user_repo_mock.get_by_email.assert_called_once_with(data.email)

        user_repo_mock.add.assert_not_called()

        category_repo_mock.add_all.assert_not_awaited()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_register_existing_username(
        self,
        user_service: UserService,
        user_repo_mock: UserRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        data: UserCreate,
    ):
        user_repo_mock.get_by_email.return_value = None
        user_repo_mock.get_by_username.return_value = existing_user

        with pytest.raises(ValueExistsException, match="User with this username already exists"):
            await user_service.register_user(data)

        user_repo_mock.get_by_username.assert_called_once_with(data.username)

        user_repo_mock.add.assert_not_called()

        category_repo_mock.add_all.assert_not_awaited()

        unit_of_work_mock.commit.assert_not_awaited()


class TestAuthenticate:
    @pytest.fixture
    def data(
        self,
        existing_user: User,
        plain_existing_user_password: str,
    ):
        return UserLogin(
            email=existing_user.email,
            password=plain_existing_user_password,
        )

    @pytest.mark.parametrize(
        "user_agent",
        ["unit-test-agent", None],
        ids=["with_user_agent", "without_user_agent"],
    )
    async def test_authenticate_success(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_repo_mock: UserRepository,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        data: UserLogin,
        user_agent: str | None,
    ):
        mocked_token = "mocked_token"
        session_id = uuid.uuid4()
        now = datetime.now(UTC)
        session_idle_days = 7
        refresh_secret = "login-refresh-secret"

        mocker.patch("app.services.user_service.utc_now", return_value=now)
        mocker.patch("app.services.user_service.settings.SESSION_IDLE_DAYS", session_idle_days)
        mocker.patch("app.services.user_service.uuid4", return_value=session_id)
        mocker.patch(
            "app.services.user_service.generate_refresh_secret", return_value=refresh_secret
        )

        def persist_user_session(user_session: UserSession) -> UserSession:
            assert user_session.refresh_token_hash == hash_refresh_secret(refresh_secret)
            return user_session

        mock_password = mocker.patch("app.services.user_service.verify_password", return_value=True)

        mock_token = mocker.patch(
            "app.services.user_service.create_access_token", return_value=mocked_token
        )

        user_repo_mock.get_by_email.return_value = existing_user
        user_repo_mock.get_by_id_for_update.return_value = existing_user
        user_session_repo_mock.add.side_effect = persist_user_session

        result = await user_service.authenticate(data, user_agent=user_agent)

        created_session = user_session_repo_mock.add.await_args.args[0]

        assert result.access_token == mocked_token
        parsed_token = parse_refresh_token(result.refresh_token)
        assert parsed_token is not None
        assert parsed_token.session_id == session_id
        assert parsed_token.secret == refresh_secret
        assert verify_refresh_token_signature(*parsed_token)
        assert created_session.refresh_token_hash != refresh_secret

        assert isinstance(created_session, UserSession)

        assert_model_fields(
            created_session,
            id=session_id,
            user_id=existing_user.id,
            user_agent=user_agent,
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=session_idle_days),
            revoked_at=None,
            refresh_token_hash=hash_refresh_secret(refresh_secret),
        )

        user_repo_mock.get_by_email.assert_awaited_once_with(data.email)
        user_repo_mock.get_by_id_for_update.assert_awaited_once_with(existing_user.id)

        mock_password.assert_called_once_with(data.password, existing_user.hashed_password)

        user_session_repo_mock.delete_expired_sessions.assert_awaited_once_with(
            existing_user.id, now
        )

        user_session_repo_mock.add.assert_awaited_once_with(created_session)

        unit_of_work_mock.commit.assert_awaited_once()

        mock_token.assert_called_once_with({"sub": str(existing_user.id), "sid": str(session_id)})

    async def test_authenticate_truncates_user_agent(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_repo_mock: UserRepository,
        user_session_repo_mock: UserSessionRepository,
        existing_user: User,
        data: UserLogin,
    ):
        mocked_token = "mocked_token"
        expected_user_agent = "a" * USER_AGENT_MAX_LENGTH
        user_agent = expected_user_agent + "b"

        mocker.patch("app.services.user_service.verify_password", return_value=True)
        mocker.patch("app.services.user_service.create_access_token", return_value=mocked_token)

        user_repo_mock.get_by_email.return_value = existing_user
        user_repo_mock.get_by_id_for_update.return_value = existing_user

        await user_service.authenticate(data, user_agent=user_agent)

        created_session = user_session_repo_mock.add.await_args.args[0]

        assert created_session.user_agent == expected_user_agent

        assert len(created_session.user_agent) == USER_AGENT_MAX_LENGTH

        user_session_repo_mock.add.assert_awaited_once_with(created_session)

    async def test_authenticate_not_found_user(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_repo_mock: UserRepository,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        data: UserLogin,
    ):
        mock_password = mocker.patch(
            "app.services.user_service.verify_password", return_value=False
        )

        user_repo_mock.get_by_email.return_value = None

        with pytest.raises(AuthenticationException, match=re.escape(INVALID_CREDENTIALS_MESSAGE)):
            await user_service.authenticate(data, user_agent=None)

        user_repo_mock.get_by_email.assert_awaited_once_with(data.email)
        user_repo_mock.get_by_id_for_update.assert_not_awaited()

        mock_password.assert_called_once_with(data.password, DUMMY_PASSWORD_HASH)

        user_session_repo_mock.add.assert_not_awaited()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_authenticate_wrong_password(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_repo_mock: UserRepository,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        data: UserLogin,
    ):
        mock_password = mocker.patch(
            "app.services.user_service.verify_password", return_value=False
        )

        data.password = "wrong_password"

        user_repo_mock.get_by_email.return_value = existing_user

        with pytest.raises(AuthenticationException, match=re.escape(INVALID_CREDENTIALS_MESSAGE)):
            await user_service.authenticate(data, user_agent=None)

        user_repo_mock.get_by_email.assert_awaited_once_with(data.email)
        user_repo_mock.get_by_id_for_update.assert_not_awaited()

        mock_password.assert_called_once_with(data.password, existing_user.hashed_password)

        user_session_repo_mock.add.assert_not_awaited()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_authenticate_rejects_password_changed_after_verification(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_repo_mock: UserRepository,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        data: UserLogin,
    ):
        verified_hashed_password = existing_user.hashed_password
        changed_hashed_password = "changed-hashed-password"

        mocker.patch("app.services.user_service.verify_password", return_value=True)

        def lock_user_with_changed_password(user_id: int) -> User:
            # Mimic populate_existing: the locked re-read overwrites the same object.
            existing_user.hashed_password = changed_hashed_password
            return existing_user

        user_repo_mock.get_by_email.return_value = existing_user
        user_repo_mock.get_by_id_for_update.side_effect = lock_user_with_changed_password

        with capture_logs() as logs:
            with pytest.raises(
                AuthenticationException, match=re.escape(INVALID_CREDENTIALS_MESSAGE)
            ) as exc_info:
                await user_service.authenticate(data, user_agent=None)

        assert exc_info.value.code == ErrorCode.INVALID_CREDENTIALS
        assert existing_user.hashed_password != verified_hashed_password
        assert logs == [
            {
                "event": "user_authenticate_rejected_password_changed",
                "user_id": existing_user.id,
                "email": data.email,
                "log_level": "warning",
            }
        ]

        user_repo_mock.get_by_id_for_update.assert_awaited_once_with(existing_user.id)
        user_session_repo_mock.delete_expired_sessions.assert_not_awaited()
        user_session_repo_mock.add.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()

    async def test_authenticate_rejects_user_deleted_after_verification(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_repo_mock: UserRepository,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        data: UserLogin,
    ):
        mocker.patch("app.services.user_service.verify_password", return_value=True)

        user_repo_mock.get_by_email.return_value = existing_user
        user_repo_mock.get_by_id_for_update.return_value = None

        with capture_logs() as logs:
            with pytest.raises(
                AuthenticationException, match=re.escape(INVALID_CREDENTIALS_MESSAGE)
            ) as exc_info:
                await user_service.authenticate(data, user_agent=None)

        assert exc_info.value.code == ErrorCode.INVALID_CREDENTIALS
        assert logs == [
            {
                "event": "user_authenticate_rejected_user_deleted",
                "user_id": existing_user.id,
                "email": data.email,
                "log_level": "warning",
            }
        ]

        user_repo_mock.get_by_id_for_update.assert_awaited_once_with(existing_user.id)
        user_session_repo_mock.add.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()


class TestRefreshSession:
    async def test_refresh_session_reads_clock_after_acquiring_session_lock(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        active_user_session: UserSession,
        refresh_secret: str,
        session_now: datetime,
    ):
        events = []

        async def acquire_session_lock(session_id: uuid.UUID):
            events.append("lock")
            return active_user_session

        def read_clock():
            events.append("clock")
            return session_now

        user_session_repo_mock.get_by_id_for_update.side_effect = acquire_session_lock
        mocker.patch("app.services.user_service.utc_now", side_effect=read_clock)
        refresh_token = create_refresh_token(active_user_session.id, refresh_secret)

        await user_service.refresh_session(refresh_token)

        assert events == ["lock", "clock"]
        assert active_user_session.rotated_at == session_now
        assert active_user_session.last_used_at == session_now
        user_session_repo_mock.get_by_id_for_update.assert_awaited_once_with(active_user_session.id)

    @pytest.mark.parametrize(
        "session_age, expected_remaining_lifetime",
        [
            pytest.param(
                SESSION_TIME_OFFSET,
                timedelta(days=settings.SESSION_IDLE_DAYS),
                id="idle-window",
            ),
            pytest.param(
                timedelta(days=settings.SESSION_MAX_DAYS) - SESSION_TIME_OFFSET,
                SESSION_TIME_OFFSET,
                id="absolute-limit",
            ),
        ],
    )
    async def test_refresh_session_rotates_tokens_and_extends_expiration(
        self,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        active_user_session: UserSession,
        refresh_secret: str,
        session_now: datetime,
        session_age: timedelta,
        expected_remaining_lifetime: timedelta,
    ):
        active_user_session.created_at = session_now - session_age
        original_hash = active_user_session.refresh_token_hash
        original_created_at = active_user_session.created_at
        refresh_token = create_refresh_token(active_user_session.id, refresh_secret)
        user_session_repo_mock.get_by_id_for_update.return_value = active_user_session
        expected_expiration = session_now + expected_remaining_lifetime

        result = await user_service.refresh_session(refresh_token)

        parsed_token = parse_refresh_token(result.refresh_token)
        assert parsed_token is not None
        session_id, new_secret, signature = parsed_token
        assert verify_refresh_token_signature(session_id, new_secret, signature)
        assert session_id == active_user_session.id
        assert new_secret != refresh_secret
        assert active_user_session.refresh_token_hash != original_hash
        assert active_user_session.refresh_token_hash == hash_refresh_secret(new_secret)
        assert active_user_session.previous_refresh_token_hash == original_hash
        assert active_user_session.rotated_at == session_now
        assert active_user_session.last_used_at == session_now
        assert active_user_session.created_at == original_created_at
        assert active_user_session.expires_at == expected_expiration
        payload = verify_token(result.access_token)
        assert payload["sub"] == str(existing_user.id)
        assert payload["sid"] == str(session_id)
        user_session_repo_mock.get_by_id_for_update.assert_awaited_once_with(session_id)
        user_session_repo_mock.get_active_with_user.assert_not_awaited()
        user_session_repo_mock.update.assert_awaited_once_with(active_user_session)
        unit_of_work_mock.commit.assert_awaited_once()

    @pytest.mark.parametrize("token", ["", "malformed-token", "invalid-uuid.secret.signature"])
    async def test_refresh_session_rejects_malformed_token(
        self,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        token: str,
    ):
        with capture_logs() as logs:
            with pytest.raises(
                AuthenticationException, match="Invalid or expired token"
            ) as exc_info:
                await user_service.refresh_session(token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert logs == [{"event": "refresh_token_rejected_malformed", "log_level": "warning"}]
        user_session_repo_mock.get_by_id_for_update.assert_not_awaited()
        user_session_repo_mock.update.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()

    @pytest.mark.parametrize(
        "signature", ["forged-signature", "підроблений-підпис"], ids=["ascii", "non-ascii"]
    )
    async def test_refresh_session_rejects_invalid_signature_without_accessing_repository(
        self,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        active_user_session: UserSession,
        refresh_secret: str,
        signature: str,
    ):
        forged_token = forge_refresh_token(active_user_session.id, refresh_secret, signature)
        user_session_repo_mock.get_by_id_for_update.return_value = active_user_session

        with capture_logs() as logs:
            with pytest.raises(AuthenticationException, match="Invalid or expired token"):
                await user_service.refresh_session(forged_token)

        assert logs == [
            {
                "event": "refresh_token_rejected_invalid_signature",
                "session_id": str(active_user_session.id),
                "log_level": "warning",
            }
        ]
        assert active_user_session.revoked_at is None
        assert active_user_session.revoked_reason is None
        user_session_repo_mock.get_by_id_for_update.assert_not_awaited()
        user_session_repo_mock.update.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()

    async def test_refresh_session_rejects_missing_session(
        self,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        active_user_session: UserSession,
        refresh_secret: str,
        session_now: datetime,
    ):
        refresh_token = create_refresh_token(active_user_session.id, refresh_secret)
        user_session_repo_mock.get_by_id_for_update.return_value = None

        with capture_logs() as logs:
            with pytest.raises(AuthenticationException, match="Invalid or expired token"):
                await user_service.refresh_session(refresh_token)

        assert logs == [
            {
                "event": "refresh_token_rejected_session_not_found",
                "session_id": str(active_user_session.id),
                "log_level": "warning",
            }
        ]

        user_session_repo_mock.get_by_id_for_update.assert_awaited_once_with(active_user_session.id)
        user_session_repo_mock.update.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()

    @pytest.mark.parametrize("revoked_reason", list(SessionRevocationReason))
    async def test_refresh_session_rejects_revoked_session_before_checking_expiration(
        self,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        active_user_session: UserSession,
        refresh_secret: str,
        session_now: datetime,
        revoked_reason: SessionRevocationReason,
    ):
        revoked_at = session_now - SESSION_TIME_OFFSET
        active_user_session.revoked_at = revoked_at
        active_user_session.revoked_reason = revoked_reason
        active_user_session.expires_at = session_now
        user_session_repo_mock.get_by_id_for_update.return_value = active_user_session
        refresh_token = create_refresh_token(active_user_session.id, refresh_secret)

        with capture_logs() as logs:
            with pytest.raises(AuthenticationException, match="Invalid or expired token"):
                await user_service.refresh_session(refresh_token)

        assert logs == [
            {
                "event": "refresh_token_used_on_revoked_session",
                "session_id": str(active_user_session.id),
                "revoked_reason": revoked_reason.value,
                "log_level": "warning",
            }
        ]
        assert active_user_session.revoked_at == revoked_at
        assert active_user_session.revoked_reason == revoked_reason
        user_session_repo_mock.update.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()

    @pytest.mark.parametrize(
        "elapsed_since_expiration",
        [SESSION_TIME_OFFSET, timedelta(0)],
        ids=["expired", "at-boundary"],
    )
    async def test_refresh_session_rejects_expired_session(
        self,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        active_user_session: UserSession,
        refresh_secret: str,
        session_now: datetime,
        elapsed_since_expiration: timedelta,
    ):
        active_user_session.expires_at = session_now - elapsed_since_expiration
        user_session_repo_mock.get_by_id_for_update.return_value = active_user_session
        refresh_token = create_refresh_token(active_user_session.id, refresh_secret)

        with capture_logs() as logs:
            with pytest.raises(AuthenticationException, match="Invalid or expired token"):
                await user_service.refresh_session(refresh_token)

        assert logs == [
            {
                "event": "refresh_token_rejected_session_expired",
                "session_id": str(active_user_session.id),
                "log_level": "info",
            }
        ]
        assert active_user_session.revoked_at is None
        assert active_user_session.revoked_reason is None
        user_session_repo_mock.update.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()

    @pytest.mark.parametrize(
        "rotation_age",
        [timedelta(seconds=1), timedelta(seconds=settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS)],
        ids=["within-grace", "at-grace-boundary"],
    )
    async def test_refresh_session_previous_token_rotates_without_extending_grace(
        self,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        active_user_session: UserSession,
        refresh_secret: str,
        session_now: datetime,
        rotation_age: timedelta,
    ):
        current_hash = hash_refresh_secret("current-refresh-secret")
        previous_hash = hash_refresh_secret(refresh_secret)
        rotated_at = session_now - rotation_age
        active_user_session.refresh_token_hash = current_hash
        active_user_session.previous_refresh_token_hash = previous_hash
        active_user_session.rotated_at = rotated_at
        user_session_repo_mock.get_by_id_for_update.return_value = active_user_session
        refresh_token = create_refresh_token(active_user_session.id, refresh_secret)

        with capture_logs() as logs:
            result = await user_service.refresh_session(refresh_token)

        parsed_token = parse_refresh_token(result.refresh_token)
        assert parsed_token is not None
        session_id, new_secret, signature = parsed_token
        assert verify_refresh_token_signature(session_id, new_secret, signature)
        assert session_id == active_user_session.id
        assert active_user_session.refresh_token_hash == hash_refresh_secret(new_secret)
        assert active_user_session.refresh_token_hash != current_hash
        assert active_user_session.refresh_token_hash != previous_hash
        assert active_user_session.previous_refresh_token_hash == previous_hash
        assert active_user_session.rotated_at == rotated_at
        assert active_user_session.revoked_at is None
        assert active_user_session.revoked_reason is None
        assert active_user_session.last_used_at == session_now
        assert active_user_session.expires_at == session_now + timedelta(
            days=settings.SESSION_IDLE_DAYS
        )
        assert verify_token(result.access_token)["sid"] == str(session_id)
        assert logs == [
            {
                "event": "user_session_refresh_success",
                "session_id": str(session_id),
                "match": "previous_in_grace",
                "log_level": "info",
            }
        ]
        user_session_repo_mock.get_by_id_for_update.assert_awaited_once_with(session_id)
        user_session_repo_mock.update.assert_awaited_once_with(active_user_session)
        unit_of_work_mock.commit.assert_awaited_once()

    @pytest.mark.parametrize(
        "rotation_state",
        ["never-rotated", "unrelated-previous", "grace-expired", "missing-rotated-at"],
    )
    async def test_refresh_session_commits_revocation_before_rejecting_reused_token(
        self,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        active_user_session: UserSession,
        session_now: datetime,
        rotation_state: str,
    ):
        wrong_secret = "wrong-refresh-secret"
        refresh_token = create_refresh_token(active_user_session.id, wrong_secret)
        grace_interval = timedelta(seconds=settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS)
        boundary_offset = timedelta(microseconds=1)
        if rotation_state == "unrelated-previous":
            active_user_session.previous_refresh_token_hash = hash_refresh_secret("previous-secret")
            active_user_session.rotated_at = session_now
        elif rotation_state in {"grace-expired", "missing-rotated-at"}:
            active_user_session.previous_refresh_token_hash = hash_refresh_secret(wrong_secret)
            if rotation_state == "grace-expired":
                active_user_session.rotated_at = session_now - grace_interval - boundary_offset
        original_hash = active_user_session.refresh_token_hash
        original_last_used_at = active_user_session.last_used_at
        original_expires_at = active_user_session.expires_at
        user_session_repo_mock.get_by_id_for_update.return_value = active_user_session

        def commit_revocation():
            user_session_repo_mock.update.assert_awaited_once_with(active_user_session)
            assert active_user_session.revoked_at == session_now
            assert active_user_session.revoked_reason == SessionRevocationReason.REUSE_DETECTED

        unit_of_work_mock.commit.side_effect = commit_revocation

        with capture_logs() as logs:
            with pytest.raises(AuthenticationException, match="Invalid or expired token"):
                await user_service.refresh_session(refresh_token)

        assert logs == [
            {
                "event": "refresh_token_reuse_detected",
                "session_id": str(active_user_session.id),
                "user_id": active_user_session.user_id,
                "log_level": "warning",
            }
        ]

        assert active_user_session.refresh_token_hash == original_hash
        assert active_user_session.last_used_at == original_last_used_at
        assert active_user_session.expires_at == original_expires_at
        assert active_user_session.revoked_at == session_now
        assert active_user_session.revoked_reason == SessionRevocationReason.REUSE_DETECTED
        user_session_repo_mock.get_by_id_for_update.assert_awaited_once_with(active_user_session.id)
        unit_of_work_mock.commit.assert_awaited_once()


class TestLogout:
    async def test_logout_revokes_session(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        active_user_session: UserSession,
        refresh_secret: str,
        session_now: datetime,
    ):
        events = []

        async def acquire_session_lock(session_id: uuid.UUID):
            events.append("lock")
            return active_user_session

        def read_clock():
            events.append("clock")
            return session_now

        user_session_repo_mock.get_by_id_for_update.side_effect = acquire_session_lock
        mocker.patch("app.services.user_service.utc_now", side_effect=read_clock)
        refresh_token = create_refresh_token(active_user_session.id, refresh_secret)

        result = await user_service.logout(refresh_token)

        assert events == ["lock", "clock"]
        assert result is None
        assert active_user_session.revoked_at == session_now
        assert active_user_session.revoked_reason == SessionRevocationReason.LOGOUT
        user_session_repo_mock.get_by_id_for_update.assert_awaited_once_with(active_user_session.id)
        user_session_repo_mock.get_active_with_user.assert_not_awaited()
        user_session_repo_mock.update.assert_awaited_once_with(active_user_session)
        unit_of_work_mock.commit.assert_awaited_once()

    @pytest.mark.parametrize("token", ["", "malformed-token", "invalid-uuid.secret.signature"])
    async def test_logout_ignores_malformed_token(
        self,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        token: str,
    ):
        with capture_logs() as logs:
            result = await user_service.logout(token)

        assert result is None
        assert logs == [{"event": "refresh_token_rejected_malformed", "log_level": "warning"}]
        user_session_repo_mock.get_by_id_for_update.assert_not_awaited()
        user_session_repo_mock.update.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()

    @pytest.mark.parametrize(
        "signature", ["forged-signature", "підроблений-підпис"], ids=["ascii", "non-ascii"]
    )
    async def test_logout_ignores_invalid_signature_without_accessing_repository(
        self,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        active_user_session: UserSession,
        refresh_secret: str,
        signature: str,
    ):
        forged_token = forge_refresh_token(active_user_session.id, refresh_secret, signature)
        user_session_repo_mock.get_by_id_for_update.return_value = active_user_session

        with capture_logs() as logs:
            result = await user_service.logout(forged_token)

        assert result is None
        assert logs == [
            {
                "event": "refresh_token_rejected_invalid_signature",
                "session_id": str(active_user_session.id),
                "log_level": "warning",
            }
        ]
        assert active_user_session.revoked_at is None
        assert active_user_session.revoked_reason is None
        user_session_repo_mock.get_by_id_for_update.assert_not_awaited()
        user_session_repo_mock.update.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()

    @pytest.mark.parametrize(
        "session_exists", [False, True], ids=["missing-session", "wrong-secret"]
    )
    async def test_logout_ignores_unmatched_token(
        self,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        active_user_session: UserSession,
        session_exists: bool,
    ):
        wrong_secret = "wrong-refresh-secret"
        refresh_token = create_refresh_token(active_user_session.id, wrong_secret)
        user_session_repo_mock.get_by_id_for_update.return_value = (
            active_user_session if session_exists else None
        )
        expected_event = (
            "logout_ignored_stale_refresh_token"
            if session_exists
            else "refresh_token_rejected_session_not_found"
        )

        with capture_logs() as logs:
            result = await user_service.logout(refresh_token)

        assert result is None
        assert logs == [
            {
                "event": expected_event,
                "session_id": str(active_user_session.id),
                "log_level": "warning",
            }
        ]
        assert active_user_session.revoked_at is None
        user_session_repo_mock.update.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()

    async def test_logout_ignores_previous_token_in_grace_without_changing_session(
        self,
        user_service: UserService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        active_user_session: UserSession,
        refresh_secret: str,
        session_now: datetime,
    ):
        current_hash = hash_refresh_secret("current-refresh-secret")
        previous_hash = hash_refresh_secret(refresh_secret)
        rotated_at = session_now - timedelta(seconds=1)
        active_user_session.refresh_token_hash = current_hash
        active_user_session.previous_refresh_token_hash = previous_hash
        active_user_session.rotated_at = rotated_at
        original_last_used_at = active_user_session.last_used_at
        original_expires_at = active_user_session.expires_at
        user_session_repo_mock.get_by_id_for_update.return_value = active_user_session
        refresh_token = create_refresh_token(active_user_session.id, refresh_secret)

        with capture_logs() as logs:
            result = await user_service.logout(refresh_token)

        assert result is None
        assert_model_fields(
            active_user_session,
            refresh_token_hash=current_hash,
            previous_refresh_token_hash=previous_hash,
            rotated_at=rotated_at,
            last_used_at=original_last_used_at,
            expires_at=original_expires_at,
            revoked_at=None,
            revoked_reason=None,
        )
        assert logs == [
            {
                "event": "logout_ignored_stale_refresh_token",
                "session_id": str(active_user_session.id),
                "log_level": "warning",
            }
        ]
        user_session_repo_mock.get_by_id_for_update.assert_awaited_once_with(active_user_session.id)
        user_session_repo_mock.update.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()


class TestUpdateUsername:
    @pytest.fixture
    def data(
        self,
    ):
        return UsernameUpdate(new_username="test_user")

    async def test_update_username_success(
        self,
        user_service: UserService,
        user_repo_mock: UserRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        data: UsernameUpdate,
    ):
        user_repo_mock.get_by_id.return_value = existing_user
        user_repo_mock.get_by_username.return_value = None

        user_repo_mock.update.side_effect = as_persisted

        result = await user_service.update_username(data, existing_user.id)

        call_args = user_repo_mock.update.call_args[0][0]

        assert result == UserResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            email=existing_user.email,
            username=data.new_username,
        )

        user_repo_mock.get_by_id.assert_called_once_with(existing_user.id)

        user_repo_mock.get_by_username.assert_called_once_with(data.new_username)

        user_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_username_username_belongs_to_other_user(
        self,
        user_service: UserService,
        user_repo_mock: UserRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        data: UsernameUpdate,
    ):
        user_repo_mock.get_by_id.return_value = existing_user

        duplicate_user = make_user(
            id=existing_user.id + 1,
            email="other@test.com",
            username=data.new_username,
            hashed_password="hashed_password",
        )
        user_repo_mock.get_by_username.return_value = duplicate_user

        with pytest.raises(ValueExistsException, match="Username is already taken"):
            await user_service.update_username(data, existing_user.id)

        user_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_username_self_not_duplicate(
        self,
        user_service: UserService,
        user_repo_mock: UserRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        data: UsernameUpdate,
    ):
        data.new_username = existing_user.username
        user_repo_mock.get_by_id.return_value = existing_user
        user_repo_mock.get_by_username.return_value = existing_user
        user_repo_mock.update.return_value = existing_user

        result = await user_service.update_username(data, existing_user.id)

        assert result == UserResponse.model_validate(existing_user)

        call_args = user_repo_mock.update.call_args[0][0]
        assert_model_fields(
            call_args,
            email=existing_user.email,
            username=data.new_username,
        )

        user_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()


class TestUpdatePassword:
    @pytest.fixture
    def data(self, plain_existing_user_password: str):
        return PasswordUpdate(
            current_password=plain_existing_user_password,
            new_password="Password1234!",
        )

    async def test_update_password_rejects_missing_user(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_repo_mock: UserRepository,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        active_user_session: UserSession,
        data: PasswordUpdate,
    ):
        user_repo_mock.get_by_id_for_update.return_value = None
        mock_password = mocker.patch("app.services.user_service.verify_password")
        mock_hash = mocker.patch("app.services.user_service.hash_password")

        with pytest.raises(
            AuthenticationException, match=f"^{re.escape(USER_NO_LONGER_EXISTS_MESSAGE)}$"
        ) as exc_info:
            await user_service.update_password(
                data, existing_user.id, current_session_id=active_user_session.id
            )

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        user_repo_mock.get_by_id_for_update.assert_awaited_once_with(existing_user.id)
        user_repo_mock.get_by_id.assert_not_awaited()
        mock_password.assert_not_called()
        mock_hash.assert_not_called()
        user_repo_mock.update.assert_not_awaited()
        user_session_repo_mock.revoke_active_except.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()

    @pytest.mark.parametrize("revoked_count", [0, 2], ids=["no-other-sessions", "revoked"])
    async def test_update_password_success(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_repo_mock: UserRepository,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        active_user_session: UserSession,
        session_now: datetime,
        data: PasswordUpdate,
        revoked_count: int,
    ):
        user_repo_mock.get_by_id_for_update.return_value = existing_user
        user_session_repo_mock.revoke_active_except.return_value = revoked_count
        original_hashed_password = existing_user.hashed_password
        original_password_changed_at = existing_user.password_changed_at
        hashed_password = "hashed"

        mock_password = mocker.patch("app.services.user_service.verify_password", return_value=True)

        mock_hash = mocker.patch(
            "app.services.user_service.hash_password", return_value=hashed_password
        )

        async def commit_password_and_revocation():
            user_repo_mock.update.assert_awaited_once_with(existing_user)
            user_session_repo_mock.revoke_active_except.assert_awaited_once_with(
                existing_user.id,
                keep_session_id=active_user_session.id,
                now=session_now,
                reason=SessionRevocationReason.PASSWORD_CHANGED,
            )
            assert existing_user.hashed_password == hashed_password
            assert existing_user.password_changed_at == session_now
            assert logs == []

        unit_of_work_mock.commit.side_effect = commit_password_and_revocation

        with capture_logs() as logs:
            result = await user_service.update_password(
                data, existing_user.id, current_session_id=active_user_session.id
            )

        assert result is None

        user_repo_mock.get_by_id_for_update.assert_awaited_once_with(existing_user.id)
        user_repo_mock.get_by_id.assert_not_awaited()

        call_args = user_repo_mock.update.call_args[0][0]
        assert_model_fields(
            call_args,
            email=existing_user.email,
            username=existing_user.username,
            hashed_password=hashed_password,
        )

        mock_password.assert_called_once_with(data.current_password, original_hashed_password)

        mock_hash.assert_called_once_with(data.new_password)

        assert original_password_changed_at < existing_user.password_changed_at

        user_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()
        assert logs == [
            {
                "event": "password_update_success",
                "user_id": existing_user.id,
                "revoked_count": revoked_count,
                "log_level": "info",
            }
        ]

    async def test_update_password_wrong_current(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_repo_mock: UserRepository,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        active_user_session: UserSession,
        data: PasswordUpdate,
    ):
        data.current_password = "wrong_password"

        user_repo_mock.get_by_id_for_update.return_value = existing_user

        mock_password = mocker.patch(
            "app.services.user_service.verify_password", return_value=False
        )

        with pytest.raises(AuthenticationException, match="Current password is incorrect"):
            await user_service.update_password(
                data, existing_user.id, current_session_id=active_user_session.id
            )

        user_repo_mock.get_by_id_for_update.assert_awaited_once_with(existing_user.id)
        user_repo_mock.get_by_id.assert_not_awaited()
        mock_password.assert_called_once_with(data.current_password, existing_user.hashed_password)

        user_repo_mock.update.assert_not_called()
        user_session_repo_mock.revoke_active_except.assert_not_awaited()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_password_does_not_commit_when_session_revocation_fails(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_repo_mock: UserRepository,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        active_user_session: UserSession,
        data: PasswordUpdate,
    ):
        user_repo_mock.get_by_id_for_update.return_value = existing_user
        mocker.patch("app.services.user_service.verify_password", return_value=True)
        mocker.patch("app.services.user_service.hash_password", return_value="new-hashed-password")
        revocation_error = RuntimeError("Session revocation failed")
        user_session_repo_mock.revoke_active_except.side_effect = revocation_error

        with pytest.raises(RuntimeError) as exc_info:
            await user_service.update_password(
                data, existing_user.id, current_session_id=active_user_session.id
            )

        assert exc_info.value is revocation_error
        user_repo_mock.get_by_id_for_update.assert_awaited_once_with(existing_user.id)
        user_repo_mock.get_by_id.assert_not_awaited()
        user_session_repo_mock.revoke_active_except.assert_awaited_once()
        unit_of_work_mock.commit.assert_not_awaited()
