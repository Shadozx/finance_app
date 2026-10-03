import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pytest_mock import MockerFixture

from app.core import UnitOfWork
from app.core.exceptions import AuthenticationException, ValueExistsException
from app.core.security import DUMMY_PASSWORD_HASH
from app.models import USER_AGENT_MAX_LENGTH, User, UserSession
from app.repositories import CategoryRepository, UserRepository, UserSessionRepository
from app.schemas import PasswordUpdate, UserCreate, UserLogin, UsernameUpdate, UserResponse
from app.services import UserService
from app.services.default_categories import DEFAULT_CATEGORIES
from tests.units.services.helpers import (
    as_persisted,
    as_persisted_all,
    assert_model_fields,
    make_user,
)


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

        mocker.patch("app.services.user_service.utc_now", return_value=now)
        mocker.patch("app.services.user_service.settings.SESSION_IDLE_DAYS", session_idle_days)

        def persist_user_session(user_session: UserSession) -> UserSession:
            user_session.id = session_id
            return user_session

        mock_password = mocker.patch("app.services.user_service.verify_password", return_value=True)

        mock_token = mocker.patch(
            "app.services.user_service.create_access_token", return_value=mocked_token
        )

        user_repo_mock.get_by_email.return_value = existing_user
        user_session_repo_mock.add.side_effect = persist_user_session

        result = await user_service.authenticate(data, user_agent=user_agent)

        created_session = user_session_repo_mock.add.await_args.args[0]

        assert result == mocked_token

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
        )

        user_repo_mock.get_by_email.assert_awaited_once_with(data.email)

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
        persisted_session = UserSession(id=uuid.uuid4(), user_id=existing_user.id)

        mocker.patch("app.services.user_service.verify_password", return_value=True)
        mocker.patch("app.services.user_service.create_access_token", return_value=mocked_token)

        user_repo_mock.get_by_email.return_value = existing_user
        user_session_repo_mock.add.return_value = persisted_session

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

        with pytest.raises(AuthenticationException, match="Invalid email or password"):
            await user_service.authenticate(data, user_agent=None)

        user_repo_mock.get_by_email.assert_called_once_with(data.email)

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

        with pytest.raises(AuthenticationException, match="Invalid email or password"):
            await user_service.authenticate(data, user_agent=None)

        user_repo_mock.get_by_email.assert_called_once_with(data.email)

        mock_password.assert_called_once_with(data.password, existing_user.hashed_password)

        user_session_repo_mock.add.assert_not_awaited()

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

    async def test_update_password_success(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_repo_mock: UserRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        data: PasswordUpdate,
    ):
        user_repo_mock.get_by_id.return_value = existing_user
        original_hashed_password = existing_user.hashed_password
        original_password_changed_at = existing_user.password_changed_at
        hashed_password = "hashed"

        mock_password = mocker.patch("app.services.user_service.verify_password", return_value=True)

        mock_hash = mocker.patch(
            "app.services.user_service.hash_password", return_value=hashed_password
        )

        result = await user_service.update_password(data, existing_user.id)

        assert result is None

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

    async def test_update_password_wrong_current(
        self,
        mocker: MockerFixture,
        user_service: UserService,
        user_repo_mock: UserRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        data: PasswordUpdate,
    ):
        data.current_password = "wrong_password"

        user_repo_mock.get_by_id.return_value = existing_user

        mock_password = mocker.patch(
            "app.services.user_service.verify_password", return_value=False
        )

        with pytest.raises(AuthenticationException, match="Current password is incorrect"):
            await user_service.update_password(data, existing_user.id)

        mock_password.assert_called_once_with(data.current_password, existing_user.hashed_password)

        user_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()
