import pytest
from pytest_mock import MockerFixture

from app.repositories import UserRepository
from app.services import UserService
from app.models import User
from app.schemas import UserCreate, UserLogin, UserResponse
from app.core.exceptions import ValueExistsException, AuthenticationException


class TestRegister:
    async def test_register_success(
            self,
            existing_user: User,
            plain_existing_user_password: str,
            user_repo_mock: UserRepository,
            user_service: UserService
    ):
        user_repo_mock.get_by_email.return_value = None
        user_repo_mock.get_by_username.return_value = None

        user = UserCreate(
            email=existing_user.email,
            username=existing_user.username,
            password=plain_existing_user_password,
        )

        user_repo_mock.create.return_value = existing_user

        actual = await user_service.register_user(user)

        assert actual == UserResponse.model_validate(existing_user)

        user_repo_mock.create.assert_called_once()

    async def test_register_existing_email(
            self,
            existing_user: User,
            plain_existing_user_password: str,
            user_repo_mock: UserRepository,
            user_service: UserService
    ):
        user_repo_mock.get_by_email.return_value = existing_user
        user_repo_mock.get_by_username.return_value = None

        user = UserCreate(
            email=existing_user.email,
            username=existing_user.username,
            password=plain_existing_user_password,
        )

        with pytest.raises(ValueExistsException, match="User with this email already exists"):
            await user_service.register_user(user)

        user_repo_mock.create.assert_not_called()

    async def test_register_existing_username(
            self,
            existing_user: User,
            plain_existing_user_password: str,
            user_repo_mock: UserRepository,
            user_service: UserService
    ):
        user_repo_mock.get_by_email.return_value = None
        user_repo_mock.get_by_username.return_value = existing_user

        user = UserCreate(
            email=existing_user.email,
            username=existing_user.username,
            password=plain_existing_user_password,
        )

        with pytest.raises(ValueExistsException, match="User with this username already exists"):
            await user_service.register_user(user)

        user_repo_mock.create.assert_not_called()


class TestAuthenticate:
    async def test_authenticate_success(
            self,
            mocker: MockerFixture,
            existing_user: User,
            plain_existing_user_password: str,
            user_repo_mock: UserRepository,
            user_service: UserService
    ):
        expected = "mocked_token"
        mock_token = mocker.patch("app.services.user_service.create_access_token", return_value="mocked_token")

        user_repo_mock.get_by_email.return_value = existing_user

        data = UserLogin(
            email=existing_user.email,
            password=plain_existing_user_password,
        )

        actual = await user_service.authenticate(data)

        assert actual == expected

        user_repo_mock.get_by_email.assert_called_once_with(data.email)

        mock_token.assert_called_once_with({"sub": str(existing_user.id)})

    async def test_authenticate_not_found_user(
            self,
            user_repo_mock: UserRepository,
            user_service: UserService
    ):

        data = UserLogin(
            email="user@test.com",
            password="password",
        )

        user_repo_mock.get_by_email.return_value = None

        with pytest.raises(AuthenticationException, match="Invalid email or password"):
            await user_service.authenticate(data)

        user_repo_mock.get_by_email.assert_called_once_with(data.email)

    async def test_authenticate_wrong_password(
            self,
            mocker: MockerFixture,
            existing_user: User,
            user_repo_mock: UserRepository,
            user_service: UserService
    ):
        mock_password = mocker.patch("app.services.user_service.verify_password", return_value=False)


        data = UserLogin(
            email=existing_user.email,
            password="wrong_password",
        )

        user_repo_mock.get_by_email.return_value = existing_user

        with pytest.raises(AuthenticationException, match="Invalid email or password"):
            await user_service.authenticate(data)

        user_repo_mock.get_by_email.assert_called_once_with(data.email)

        mock_password.assert_called_once_with(data.password, existing_user.hashed_password)

