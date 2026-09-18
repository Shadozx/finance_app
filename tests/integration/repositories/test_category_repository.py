from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, User
from app.repositories import CategoryRepository, UserRepository
from app.schemas import CategoryStatus


@pytest.fixture
async def archived_category(category_repository: CategoryRepository, user: User):
    category = Category(
        name="Archived Category",
        user_id=user.id,
        archived_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    return await category_repository.add(category)


@pytest.fixture
async def categories_for_ordering(
    category_repository: CategoryRepository,
    user: User,
):
    active_names = ("Transport", "Food")
    archived_names = ("Salary", "Auto")

    for name in active_names:
        await category_repository.add(Category(name=name, user_id=user.id))

    for name in archived_names:
        category = await category_repository.add(Category(name=name, user_id=user.id))
        await category_repository.archive(category)


class TestAdd:
    async def test_add(
        self,
        category_repository: CategoryRepository,
        user: User,
    ):
        new_category = Category(
            name="Salary",
            user_id=user.id,
        )

        created_category = await category_repository.add(new_category)

        assert created_category.id is not None
        assert created_category.name == new_category.name
        assert created_category.user_id == new_category.user_id

    async def test_add_duplicate_name_same_user(
        self,
        category_repository: CategoryRepository,
        category: Category,
    ):
        duplicate_category = Category(
            name=category.name,
            user_id=category.user_id,
        )

        with pytest.raises(IntegrityError):
            await category_repository.add(duplicate_category)


class TestGetById:
    async def test_get_by_id(
        self,
        category_repository: CategoryRepository,
        category: Category,
    ):
        found_category = await category_repository.get_by_id(category.id)

        assert found_category.id == category.id
        assert found_category.name == category.name

    async def test_get_by_id_not_found(self, category_repository: CategoryRepository):
        found_category = await category_repository.get_by_id(999)

        assert found_category is None


class TestGetByUser:
    async def test_get_by_user_default_returns_active_categories(
        self,
        category_repository: CategoryRepository,
        category: Category,
    ):
        new_category = Category(
            name="Lunch",
            user_id=category.user_id,
        )

        await category_repository.add(new_category)

        categories = await category_repository.get_by_user(category.user_id)

        assert len(categories) == 2

        category_ids = {cat.id for cat in categories}

        assert category.id in category_ids
        assert new_category.id in category_ids
        assert all(cat.archived_at is None for cat in categories)

    @pytest.mark.parametrize(
        "status, expected_names",
        [
            (CategoryStatus.ACTIVE, ["Food", "Transport"]),
            (CategoryStatus.ARCHIVED, ["Auto", "Salary"]),
            (CategoryStatus.ALL, ["Auto", "Food", "Salary", "Transport"]),
        ],
    )
    async def test_get_by_user_ordered_by_name(
        self,
        category_repository: CategoryRepository,
        user: User,
        categories_for_ordering,
        status: CategoryStatus,
        expected_names: list[str],
    ):
        user_categories = await category_repository.get_by_user(user.id, status=status)

        assert [category.name for category in user_categories] == expected_names

    async def test_get_by_user_pagination_does_not_repeat_or_skip(
        self,
        category_repository: CategoryRepository,
        user: User,
        categories_for_ordering,
    ):
        page_size = 2

        first_page = await category_repository.get_by_user(
            user.id, status=CategoryStatus.ALL, limit=page_size, offset=0
        )
        second_page = await category_repository.get_by_user(
            user.id, status=CategoryStatus.ALL, limit=page_size, offset=page_size
        )
        all_categories = await category_repository.get_by_user(user.id, status=CategoryStatus.ALL)

        returned_names = [category.name for category in first_page + second_page]

        assert returned_names == [category.name for category in all_categories]

    async def test_get_by_user_pagination_limit(
        self,
        category_repository: CategoryRepository,
        user: User,
        categories_for_ordering,
    ):
        limit = 2

        user_categories = await category_repository.get_by_user(
            user.id, status=CategoryStatus.ALL, limit=limit
        )

        assert len(user_categories) == limit

    async def test_get_by_user_pagination_offset(
        self,
        category_repository: CategoryRepository,
        user: User,
        categories_for_ordering,
    ):
        offset = 2

        user_categories = await category_repository.get_by_user(
            user.id, status=CategoryStatus.ALL, offset=offset
        )

        assert [category.name for category in user_categories] == ["Salary", "Transport"]

    async def test_get_by_user_default_excludes_archived_categories(
        self,
        category_repository: CategoryRepository,
        category: Category,
        archived_category: Category,
    ):
        categories = await category_repository.get_by_user(category.user_id)

        assert len(categories) == 1
        assert categories[0].id == category.id
        assert categories[0].archived_at is None

    async def test_get_by_user_returns_empty_list(
        self,
        category_repository: CategoryRepository,
        user: User,
    ):
        categories = await category_repository.get_by_user(user.id)

        assert categories == []

    async def test_get_by_user_default_returns_only_own_categories(
        self,
        test_session: AsyncSession,
        category_repository: CategoryRepository,
        category: Category,
    ):
        other_user_repository = UserRepository(test_session)
        other_user = await other_user_repository.add(
            User(
                email="other@test.com",
                username="other",
                hashed_password="hashed",
            )
        )

        other_category = Category(
            name="Other User Category",
            user_id=other_user.id,
        )
        await category_repository.add(other_category)

        categories = await category_repository.get_by_user(category.user_id)

        assert len(categories) == 1
        assert categories[0].id == category.id
        assert categories[0].user_id == category.user_id

    async def test_get_by_user_status_archived_returns_only_archived_categories(
        self,
        category_repository: CategoryRepository,
        category: Category,
        archived_category: Category,
    ):
        categories = await category_repository.get_by_user(
            category.user_id,
            status=CategoryStatus.ARCHIVED,
        )

        assert len(categories) == 1
        assert categories[0].id == archived_category.id
        assert categories[0].archived_at is not None

    async def test_get_by_user_status_all_returns_active_and_archived_categories(
        self,
        category_repository: CategoryRepository,
        category: Category,
        archived_category: Category,
    ):
        categories = await category_repository.get_by_user(
            category.user_id,
            status=CategoryStatus.ALL,
        )

        assert len(categories) == 2

        category_ids = {cat.id for cat in categories}

        assert category.id in category_ids
        assert archived_category.id in category_ids

    async def test_get_by_user_status_all_returns_only_own_categories(
        self,
        test_session: AsyncSession,
        category_repository: CategoryRepository,
        category: Category,
        archived_category: Category,
    ):
        other_user_repository = UserRepository(test_session)
        other_user = await other_user_repository.add(
            User(
                email="other@test.com",
                username="other",
                hashed_password="hashed",
            )
        )

        other_active_category = Category(
            name="Other Active Category",
            user_id=other_user.id,
        )
        await category_repository.add(other_active_category)

        other_archived_category = Category(
            name="Other Archived Category",
            user_id=other_user.id,
            archived_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        await category_repository.add(other_archived_category)

        categories = await category_repository.get_by_user(
            category.user_id,
            status=CategoryStatus.ALL,
        )

        assert len(categories) == 2

        category_ids = {cat.id for cat in categories}

        assert category.id in category_ids
        assert archived_category.id in category_ids
        assert other_active_category.id not in category_ids
        assert other_archived_category.id not in category_ids


class TestGetByUserAndName:
    async def test_get_by_user_and_name(
        self,
        category_repository: CategoryRepository,
        category: Category,
    ):
        found_category = await category_repository.get_by_user_and_name(
            category.user_id, category.name
        )

        assert found_category.id == category.id
        assert found_category.name == category.name
        assert found_category.user_id == category.user_id

    async def test_get_by_user_and_name_finds_archived(
        self,
        category_repository: CategoryRepository,
        user: User,
        archived_category: Category,
    ):
        found_category = await category_repository.get_by_user_and_name(
            user.id, archived_category.name
        )

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
    async def test_update(self, category_repository: CategoryRepository, category: Category):
        category.name = "updated_category"

        updated_category = await category_repository.update(category)

        assert updated_category.id == category.id
        assert updated_category.name == category.name

        found_category = await category_repository.get_by_id(category.id)
        assert found_category.name == category.name
