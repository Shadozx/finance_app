import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.repositories import UserRepository


class TestAdd:
    async def test_add_persists_user(self, user_repository: UserRepository):
        user = User(
            email="testuser@test.com",
            username="testuser",
            hashed_password="hashed_password",
        )

        created_user = await user_repository.add(user)

        assert created_user.id is not None
        assert created_user.username == user.username
        assert created_user.email == user.email

    async def test_add_duplicate_email_raises_integrity_error(
        self, user_repository: UserRepository, user: User
    ):
        duplicate_user = User(
            email=user.email,
            username="duplicate_email_user",
            hashed_password="hashed_password",
        )

        with pytest.raises(IntegrityError):
            await user_repository.add(duplicate_user)

    async def test_add_duplicate_username_raises_integrity_error(
        self, user_repository: UserRepository, user: User
    ):
        duplicate_user = User(
            email="testduplicateusername@test.com",
            username=user.username,
            hashed_password="hashed_password",
        )

        with pytest.raises(IntegrityError):
            await user_repository.add(duplicate_user)


class TestGetById:
    async def test_get_by_id_returns_user(self, user_repository: UserRepository, user: User):
        found_user = await user_repository.get_by_id(user.id)

        assert found_user.id == user.id
        assert found_user.username == user.username
        assert found_user.email == user.email

    async def test_get_by_id_unknown_id_returns_none(self, user_repository: UserRepository):
        found_user = await user_repository.get_by_id(999)

        assert found_user is None


class TestGetByIdForUpdate:
    async def test_get_by_id_for_update_returns_user(
        self, user_repository: UserRepository, user: User
    ):
        found_user = await user_repository.get_by_id_for_update(user.id)

        assert found_user is not None
        assert found_user.id == user.id
        assert found_user.username == user.username
        assert found_user.email == user.email

    async def test_get_by_id_for_update_unknown_id_returns_none(
        self, user_repository: UserRepository
    ):
        unknown_user_id = 999

        found_user = await user_repository.get_by_id_for_update(unknown_user_id)

        assert found_user is None

    async def test_get_by_id_for_update_cached_user_returns_fresh_password_hash(
        self,
        user_repository: UserRepository,
        test_session: AsyncSession,
        user: User,
    ):
        original_hashed_password = user.hashed_password
        updated_hashed_password = "updated-hashed-password"
        await test_session.execute(
            update(User)
            .where(User.id == user.id)
            .values(hashed_password=updated_hashed_password)
            .execution_options(synchronize_session=False)
        )
        assert user.hashed_password == original_hashed_password

        found_user = await user_repository.get_by_id_for_update(user.id)

        assert found_user is user
        assert found_user.hashed_password == updated_hashed_password


class TestGetByEmail:
    async def test_get_by_email_returns_user(self, user_repository: UserRepository, user: User):
        found_user = await user_repository.get_by_email(user.email)

        assert found_user.id == user.id
        assert found_user.email == user.email

    async def test_get_by_email_unknown_email_returns_none(self, user_repository: UserRepository):
        found_user = await user_repository.get_by_email("wrongemail@test.com")

        assert found_user is None


class TestGetByUsername:
    async def test_get_by_username_returns_user(self, user_repository: UserRepository, user: User):
        found_user = await user_repository.get_by_username(user.username)

        assert found_user.id == user.id
        assert found_user.username == user.username

    async def test_get_by_username_unknown_username_returns_none(
        self, user_repository: UserRepository
    ):
        found_user = await user_repository.get_by_username("nonexistent")

        assert found_user is None


class TestUpdate:
    async def test_update_persists_changes(self, user_repository: UserRepository, user: User):
        user.username = "updated_user"

        updated_user = await user_repository.update(user)

        assert updated_user.id == user.id
        assert updated_user.username == user.username

        found_user = await user_repository.get_by_id(user.id)
        assert found_user.username == updated_user.username
