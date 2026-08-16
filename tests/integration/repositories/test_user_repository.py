import pytest
from sqlalchemy.exc import IntegrityError

from app.repositories import UserRepository
from app.models import User


class TestAdd:

    async def test_add_user(
            self,
            user_repository: UserRepository
    ):
        user = User(
            email="testuser@test.com",
            username="testuser",
            hashed_password="hashed_password",
        )

        created_user = await user_repository.add(user)

        assert created_user.id is not None
        assert created_user.username == user.username
        assert created_user.email == user.email

    async def test_add_user_duplicate_email(
            self,
            user_repository: UserRepository,
            user: User
    ):
        duplicate_user = User(
            email=user.email,
            username="duplicate_email_user",
            hashed_password="hashed_password",
        )

        with pytest.raises(IntegrityError):
            await user_repository.add(duplicate_user)

    async def test_add_user_duplicate_username(
            self,
            user_repository: UserRepository,
            user: User
    ):
        duplicate_user = User(
            email="testduplicateusername@test.com",
            username=user.username,
            hashed_password="hashed_password",
        )

        with pytest.raises(IntegrityError):
            await user_repository.add(duplicate_user)


class TestGetById:

    async def test_get_by_id(
            self,
            user_repository: UserRepository,
            user: User
    ):
        found_user = await user_repository.get_by_id(user.id)

        assert found_user.id == user.id
        assert found_user.username == user.username
        assert found_user.email == user.email

    async def test_get_by_id_not_found(
            self,
            user_repository: UserRepository
    ):
        found_user = await user_repository.get_by_id(999)

        assert found_user is None


class TestGetByEmail:

    async def test_get_by_email(
            self,
            user_repository: UserRepository,
            user: User
    ):
        found_user = await user_repository.get_by_email(user.email)

        assert found_user.id == user.id
        assert found_user.email == user.email

    async def test_get_by_email_not_found(
            self,
            user_repository: UserRepository
    ):
        found_user = await user_repository.get_by_email("wrongemail@test.com")

        assert found_user is None


class TestGetByUsername:

    async def test_get_by_username(
            self,
            user_repository: UserRepository,
            user: User
    ):
        found_user = await user_repository.get_by_username(user.username)

        assert found_user.id == user.id
        assert found_user.username == user.username

    async def test_get_by_username_not_found(
            self,
            user_repository: UserRepository
    ):
        found_user = await user_repository.get_by_username("nonexistent")

        assert found_user is None


class TestUpdate:

    async def test_update_user(
            self,
            user_repository: UserRepository,
            user: User
    ):
        user.username = "updated_user"

        updated_user = await user_repository.update(user)

        assert updated_user.id == user.id
        assert updated_user.username == user.username

        found_user = await user_repository.get_by_id(user.id)
        assert found_user.username == updated_user.username
