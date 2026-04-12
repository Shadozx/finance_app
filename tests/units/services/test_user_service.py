import pytest
from pytest_mock import MockerFixture

from app.repositories import UserRepository
from app.services import UserService
from app.models import User
from app.schemas import UserCreate, UserLogin, UserResponse, UsernameUpdate, PasswordUpdate
from app.core.exceptions import ValueExistsException, AuthenticationException, ValidationException
from tests.units.services.helpers import assert_model_fields


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
            existing_user: User,
            data: UserCreate
    ):
        hashed_password = "hashed"

        mock_hash = mocker.patch(
            "app.services.user_service.hash_password",
            return_value=hashed_password
        )

        user_repo_mock.get_by_email.return_value = None
        user_repo_mock.get_by_username.return_value = None

        user_repo_mock.create.return_value = existing_user

        result = await user_service.register_user(data)

        assert result == UserResponse.model_validate(existing_user)

        call_args = user_repo_mock.create.call_args[0][0]
        assert_model_fields(
            call_args,
            email=data.email,
            username=data.username,
            hashed_password=hashed_password
        )

        user_repo_mock.get_by_email.assert_called_once_with(
            data.email
        )

        user_repo_mock.get_by_username.assert_called_once_with(
            data.username
        )

        mock_hash.assert_called_once_with(data.password)

        user_repo_mock.create.assert_called_once()

    async def test_register_existing_email(
            self,
            user_service: UserService,
            user_repo_mock: UserRepository,
            existing_user: User,
            data: UserCreate
    ):
        user_repo_mock.get_by_email.return_value = existing_user

        with pytest.raises(ValueExistsException, match="User with this email already exists"):
            await user_service.register_user(data)

        user_repo_mock.get_by_email.assert_called_once_with(
            data.email
        )

        user_repo_mock.create.assert_not_called()

    async def test_register_existing_username(
            self,
            user_service: UserService,
            user_repo_mock: UserRepository,
            existing_user: User,
            data: UserCreate
    ):
        user_repo_mock.get_by_email.return_value = None
        user_repo_mock.get_by_username.return_value = existing_user

        with pytest.raises(ValueExistsException, match="User with this username already exists"):
            await user_service.register_user(data)

        user_repo_mock.get_by_username.assert_called_once_with(
            data.username
        )

        user_repo_mock.create.assert_not_called()


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

    async def test_authenticate_success(
            self,
            mocker: MockerFixture,
            user_service: UserService,
            user_repo_mock: UserRepository,
            existing_user: User,
            data: UserLogin
    ):
        mocked_token = "mocked_token"

        mock_password = mocker.patch(
            "app.services.user_service.verify_password",
            return_value=True
        )

        mock_token = mocker.patch(
            "app.services.user_service.create_access_token",
            return_value=mocked_token
        )

        user_repo_mock.get_by_email.return_value = existing_user

        result = await user_service.authenticate(data)

        assert result == mocked_token

        user_repo_mock.get_by_email.assert_called_once_with(
            data.email
        )

        mock_password.assert_called_once_with(
            data.password,
            existing_user.hashed_password
        )

        mock_token.assert_called_once_with({"sub": str(existing_user.id)})

    async def test_authenticate_not_found_user(
            self,
            user_service: UserService,
            user_repo_mock: UserRepository,
            data: UserLogin,
    ):
        user_repo_mock.get_by_email.return_value = None

        with pytest.raises(AuthenticationException, match="Invalid email or password"):
            await user_service.authenticate(data)

        user_repo_mock.get_by_email.assert_called_once_with(
            data.email
        )

    async def test_authenticate_wrong_password(
            self,
            mocker: MockerFixture,
            user_service: UserService,
            user_repo_mock: UserRepository,
            existing_user: User,
            data: UserLogin
    ):
        mock_password = mocker.patch(
            "app.services.user_service.verify_password",
            return_value=False
        )

        data.password = "wrong_password"

        user_repo_mock.get_by_email.return_value = existing_user

        with pytest.raises(AuthenticationException, match="Invalid email or password"):
            await user_service.authenticate(data)

        user_repo_mock.get_by_email.assert_called_once_with(
            data.email
        )

        mock_password.assert_called_once_with(data.password, existing_user.hashed_password)


class TestUpdateUsername:

    @pytest.fixture
    def data(
            self,
    ):
        return UsernameUpdate(
            new_username="test_user"
        )

    async def test_update_username_success(
            self,
            user_service: UserService,
            user_repo_mock: UserRepository,
            existing_user: User,
            data: UsernameUpdate
    ):
        user_repo_mock.get_by_id.return_value = existing_user
        user_repo_mock.get_by_username.return_value = None

        updated = User(
            id=existing_user.id,
            email=existing_user.email,
            username=data.new_username,
            hashed_password=existing_user.hashed_password,
            created_at=existing_user.created_at,
        )
        user_repo_mock.update.return_value = updated

        result = await user_service.update_username(
            data,
            existing_user.id
        )

        assert result == UserResponse.model_validate(updated)

        call_args = user_repo_mock.update.call_args[0][0]
        assert_model_fields(
            call_args,
            email=existing_user.email,
            username=data.new_username,
        )

        user_repo_mock.get_by_id.assert_called_once_with(
            existing_user.id
        )

        user_repo_mock.get_by_username.assert_called_once_with(
            data.new_username
        )

        user_repo_mock.update.assert_called_once()

    async def test_update_username_username_belongs_to_other_user(
            self,
            user_service: UserService,
            user_repo_mock: UserRepository,
            existing_user: User,
            data: UsernameUpdate
    ):
        user_repo_mock.get_by_id.return_value = existing_user

        duplicate_user = User(
            id=existing_user.id + 1,
            email="other@test.com",
            username=data.new_username,
            hashed_password="hashed_password",
        )
        user_repo_mock.get_by_username.return_value = duplicate_user

        with pytest.raises(ValueExistsException, match="Username is already taken"):
            await user_service.update_username(
                data,
                existing_user.id
            )

        user_repo_mock.update.assert_not_called()

    async def test_update_username_self_not_duplicate(
            self,
            user_service: UserService,
            user_repo_mock: UserRepository,
            existing_user: User,
            data: UsernameUpdate
    ):
        data.new_username = existing_user.username
        user_repo_mock.get_by_id.return_value = existing_user
        user_repo_mock.get_by_username.return_value = existing_user
        user_repo_mock.update.return_value = existing_user

        result = await user_service.update_username(
            data,
            existing_user.id
        )

        assert result == UserResponse.model_validate(existing_user)

        call_args = user_repo_mock.update.call_args[0][0]
        assert_model_fields(
            call_args,
            email=existing_user.email,
            username=data.new_username,
        )

        user_repo_mock.update.assert_called_once()


class TestUpdatePassword:

    @pytest.fixture
    def data(
            self,
            plain_existing_user_password: str
    ):
        return PasswordUpdate(
            current_password=plain_existing_user_password,
            new_password="Password1234!",
        )

    async def test_update_password_success(
            self,
            mocker: MockerFixture,
            user_service: UserService,
            user_repo_mock: UserRepository,
            existing_user: User,
            data: PasswordUpdate
    ):
        user_repo_mock.get_by_id.return_value = existing_user
        original_hashed_password = existing_user.hashed_password
        hashed_password = "hashed"

        mock_password = mocker.patch(
            "app.services.user_service.verify_password",
            return_value=True
        )

        mock_hash = mocker.patch(
            "app.services.user_service.hash_password",
            return_value=hashed_password
        )

        result = await user_service.update_password(
            data,
            existing_user.id
        )

        assert result is None

        call_args = user_repo_mock.update.call_args[0][0]
        assert_model_fields(
            call_args,
            email=existing_user.email,
            username=existing_user.username,
            hashed_password=hashed_password,
        )

        mock_password.assert_called_once_with(
            data.current_password,
            original_hashed_password
        )

        mock_hash.assert_called_once_with(data.new_password)

        user_repo_mock.update.assert_called_once()

    async def test_update_password_same_as_current(
            self,
            mocker: MockerFixture,
            user_service: UserService,
            user_repo_mock: UserRepository,
            existing_user: User,
            data: PasswordUpdate
    ):
        same_password = "Password12345!"
        data.new_password = same_password
        data.current_password = same_password

        mock_password = mocker.patch(
            "app.services.user_service.verify_password",
        )

        user_repo_mock.get_by_id.return_value = existing_user

        with pytest.raises(ValidationException, match="New password must be different from current password"):
            await user_service.update_password(
                data,
                existing_user.id
            )

        mock_password.assert_not_called()

        user_repo_mock.update.assert_not_called()

    async def test_update_password_wrong_current(
            self,
            mocker: MockerFixture,
            user_service: UserService,
            user_repo_mock: UserRepository,
            existing_user: User,
            data: PasswordUpdate
    ):
        data.current_password = "wrong_password"

        user_repo_mock.get_by_id.return_value = existing_user

        mock_password = mocker.patch(
            "app.services.user_service.verify_password",
            return_value=False
        )

        with pytest.raises(AuthenticationException, match="Current password is incorrect"):
            await user_service.update_password(
                data,
                existing_user.id
            )

        mock_password.assert_called_once_with(
            data.current_password,
            existing_user.hashed_password
        )

        user_repo_mock.update.assert_not_called()
