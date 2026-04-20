from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.repositories import UserRepository, CategoryRepository
from app.models import User, Category


@pytest.fixture
def category_repository(test_session: AsyncSession):
    return CategoryRepository(test_session)


@pytest.fixture
async def archived_category(
        category_repository: CategoryRepository,
        user: User
):
    category = Category(
        name="Archived Category",
        user_id=user.id,
        archived_at=datetime(2020, 1, 1),
    )
    return await category_repository.create(category)


class TestCreate:

    async def test_create(
            self,
            category_repository: CategoryRepository,
            user: User,
    ):
        new_category = Category(
            name="Salary",
            user_id=user.id,
        )

        created_category = await category_repository.create(new_category)

        assert created_category.id is not None
        assert created_category.name == new_category.name
        assert created_category.user_id == new_category.user_id

    async def test_create_duplicate_name_same_user(
            self,
            category_repository: CategoryRepository,
            category: Category,
    ):
        duplicate_category = Category(
            name=category.name,
            user_id=category.user_id,
        )

        with pytest.raises(IntegrityError):
            await category_repository.create(duplicate_category)


class TestGetById:
    async def test_get_by_id(
            self,
            category_repository: CategoryRepository,
            category: Category,
    ):
        found_category = await category_repository.get_by_id(category.id)

        assert found_category.id == category.id
        assert found_category.name == category.name

    async def test_get_by_id_not_found(
            self,
            category_repository: CategoryRepository
    ):
        found_category = await category_repository.get_by_id(999)

        assert found_category is None


class TestGetByUser:
    async def test_get_by_user(
            self,
            category_repository: CategoryRepository,
            category: Category,
    ):
        new_category = Category(
            name="Lunch",
            user_id=category.user_id,
        )

        await category_repository.create(new_category)

        categories = await category_repository.get_by_user(category.user_id)

        assert len(categories) == 2

        assert categories[0].name == category.name
        assert categories[1].name == new_category.name

    async def test_get_by_user_excludes_archived(
            self,
            category_repository: CategoryRepository,
            category: Category,
            archived_category: Category
    ):
        categories = await category_repository.get_by_user(category.user_id)

        assert len(categories) == 1
        assert categories[0].name == category.name

    async def test_get_by_user_empty(
            self,
            category_repository: CategoryRepository,
            user: User,
    ):
        categories = await category_repository.get_by_user(user.id)

        assert len(categories) == 0

    async def test_get_by_user_returns_only_own_categories(
            self,
            test_session: AsyncSession,
            category_repository: CategoryRepository,
            category: Category,
    ):
        other_user_repository = UserRepository(test_session)
        other_user = await other_user_repository.create(User(
            email="other@test.com",
            username="other",
            hashed_password="hashed",
        ))

        other_category = Category(
            name="Other User Category",
            user_id=other_user.id,
        )
        await category_repository.create(other_category)

        categories = await category_repository.get_by_user(category.user_id)

        assert len(categories) == 1
        assert categories[0].user_id == category.user_id


class TestGetByUserAndName:
    async def test_get_by_user_and_name(
            self,
            category_repository: CategoryRepository,
            category: Category,
    ):
        found_category = await category_repository.get_by_user_and_name(category.user_id, category.name)

        assert found_category.id == category.id
        assert found_category.name == category.name
        assert found_category.user_id == category.user_id

    async def test_get_by_user_and_name_finds_archived(
            self,
            category_repository: CategoryRepository,
            user: User,
            archived_category: Category,
    ):
        found_category = await category_repository.get_by_user_and_name(user.id, archived_category.name)

        assert found_category.id == archived_category.id
        assert found_category.name == archived_category.name
        assert found_category.user_id == archived_category.user_id

    async def test_get_by_user_and_name_not_found(
            self,
            category_repository: CategoryRepository,
            user: User,
    ):
        found_category = await category_repository.get_by_user_and_name(user.id, "wrong name")

        assert found_category is None


class TestArchive:
    async def test_archive(
            self,
            category_repository: CategoryRepository,
            category: Category,
    ):
        await category_repository.archive(category)

        archived_category = await category_repository.get_by_id(category.id)

        assert archived_category.id == category.id
        assert archived_category.name == category.name
        assert archived_category.archived_at is not None


class TestRestore:
    async def test_restore(
            self,
            category_repository: CategoryRepository,
            user: User,
            archived_category: Category,
    ):
        await category_repository.restore(archived_category)

        restored_category = await category_repository.get_by_id(archived_category.id)

        assert restored_category.id == archived_category.id
        assert restored_category.name == archived_category.name
        assert restored_category.archived_at is None


class TestUpdate:

    async def test_update(
            self,
            category_repository: CategoryRepository,
            category: Category
    ):
        category.name = "updated_category"

        updated_category = await category_repository.update(category)

        assert updated_category.id == category.id
        assert updated_category.name == category.name

        found_category = await category_repository.get_by_id(category.id)
        assert found_category.name == category.name
