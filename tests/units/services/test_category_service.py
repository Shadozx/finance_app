import datetime

import pytest

from app.models import Category
from app.repositories import CategoryRepository
from app.services import CategoryService
from app.schemas import CategoryCreate, CategoryUpdate, CategoryResponse

from app.core.exceptions import NotFoundException, ValueExistsException, NotAllowedActionException, PermissionException


class TestCreateCategory:
    async def test_create_category_success(
            self,
            category_repo_mock: CategoryRepository,
            category_service: CategoryService,
    ):
        category_repo_mock.get_by_user_and_name.return_value = None

        data = CategoryCreate(
            name="Salary",
        )

        owner = 1

        created = Category(
            id=1,
            name=data.name,
            user_id=owner,
            created_at=datetime.datetime.utcnow(),
            archived_at=None
        )

        category_repo_mock.create.return_value = created

        actual = await category_service.create_category(data, owner)

        call_args = category_repo_mock.create.call_args[0][0]
        assert isinstance(call_args, Category)
        assert call_args.user_id == created.user_id
        assert call_args.name == data.name

        assert actual == CategoryResponse.model_validate(created)

        category_repo_mock.create.assert_called_once()

    async def test_create_category_existing_category(
            self,
            existing_category: Category,
            category_repo_mock: CategoryRepository,
            category_service: CategoryService,
    ):
        category_repo_mock.get_by_user_and_name.return_value = existing_category

        data = CategoryCreate(
            name=existing_category.name,
        )

        owner = existing_category.user_id

        with pytest.raises(ValueExistsException, match="Category with this name exists"):
            await category_service.create_category(data, owner)

        category_repo_mock.create.assert_not_called()


class TestUpdateCategory:

    async def test_update_category_success(
            self,
            existing_category: Category,
            category_service: CategoryService,
            category_repo_mock: CategoryRepository,
    ):
        category_repo_mock.get_by_id.return_value = existing_category
        category_repo_mock.get_by_user_and_name.return_value = None

        data = CategoryUpdate(
            name="Salary"
        )

        updated = Category(
            id=existing_category.id,
            name=data.name,
            user_id=existing_category.user_id,
            created_at=datetime.datetime.utcnow(),
        )
        category_repo_mock.update.return_value = updated

        actual = await category_service.update_category(existing_category.id, data,
                                                        existing_category.user_id)

        assert actual == CategoryResponse.model_validate(updated)

        call_args = category_repo_mock.update.call_args[0][0]
        assert isinstance(call_args, Category)
        assert call_args.user_id == existing_category.user_id
        assert call_args.name == data.name

        category_repo_mock.update.assert_called_once()

    async def test_update_category_not_found_category(
            self,
            category_service: CategoryService,
            category_repo_mock: CategoryRepository,
    ):
        category_repo_mock.get_by_id.return_value = None

        data = CategoryUpdate(
            name="Salary",
        )
        owner = 1

        category_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Category not found"):
            await category_service.update_category(1, data, owner)

        category_repo_mock.update.assert_not_called()

    async def test_update_category_wrong_owner(
            self,
            existing_category: Category,
            category_service: CategoryService,
            category_repo_mock: CategoryRepository,
    ):
        data = CategoryUpdate(
            name="Salary",
        )

        category_repo_mock.get_by_id.return_value = existing_category

        other_user = existing_category.user_id + 1

        with pytest.raises(PermissionException, match="You don't have permission to update this category"):
            await category_service.update_category(existing_category.id, data, other_user)

        category_repo_mock.update.assert_not_called()

    async def test_update_category_duplicated_name(
            self,
            existing_category: Category,
            category_service: CategoryService,
            category_repo_mock: CategoryRepository,
    ):
        category_repo_mock.get_by_id.return_value = existing_category

        duplicate_category = Category(
            id=existing_category.id + 1,
            name="Salary",
            user_id=existing_category.user_id,
            created_at=datetime.datetime(2020, 1, 1),
        )
        category_repo_mock.get_by_user_and_name.return_value = duplicate_category

        data = CategoryUpdate(
            name=duplicate_category.name,
        )

        with pytest.raises(ValueExistsException, match="Category with this name exists"):
            await category_service.update_category(existing_category.id, data, existing_category.user_id)

        category_repo_mock.update.assert_not_called()


class TestGetUserCategories:
    async def test_get_user_categories(
            self,
            category_repo_mock: CategoryRepository,
            category_service: CategoryService,
    ):
        owner = 1

        user_categories = [
            Category(
                id=1,
                name="Salary",
                user_id=owner,
                created_at=datetime.datetime(2020, 1, 1),
            ),
            Category(
                id=2,
                name="Foods",
                user_id=owner,
                created_at=datetime.datetime(2020, 1, 2),
            )
        ]

        category_repo_mock.get_by_user.return_value = user_categories

        expected = [
            CategoryResponse.model_validate(c) for c in user_categories
        ]

        actual = await category_service.get_user_categories(owner)

        assert actual == expected

        category_repo_mock.get_by_user.assert_called_once_with(owner)

    async def test_get_user_empty_categories(
            self,
            category_repo_mock: CategoryRepository,
            category_service: CategoryService,
    ):
        owner = 1

        user_categories = []

        category_repo_mock.get_by_user.return_value = user_categories

        expected = [
            CategoryResponse.model_validate(c) for c in user_categories
        ]

        actual = await category_service.get_user_categories(owner)

        assert actual == expected

        category_repo_mock.get_by_user.assert_called_once_with(owner)


class TestArchiveCategory:
    async def test_archive_category_success(
            self,
            existing_category: Category,
            category_service: CategoryService,
            category_repo_mock: CategoryRepository,
    ):
        archived_category = Category(
            id=existing_category.id,
            name=existing_category.name,
            user_id=existing_category.user_id,
            created_at=existing_category.created_at,
            archived_at=datetime.datetime(2020, 1, 1),
        )

        category_repo_mock.get_by_id.return_value = existing_category
        category_repo_mock.archive.return_value = archived_category

        await category_service.archive_category(existing_category.id, existing_category.user_id)

        category_repo_mock.archive.assert_called_once_with(existing_category)

    async def test_archive_category_not_found_category(
            self,
            existing_category: Category,
            category_service: CategoryService,
            category_repo_mock: CategoryRepository,
    ):
        category_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Category not found"):
            await category_service.archive_category(existing_category.id, existing_category.user_id)

        category_repo_mock.archive.assert_not_called()

    async def test_archive_category_wrong_owner(
            self,
            existing_category: Category,
            category_service: CategoryService,
            category_repo_mock: CategoryRepository,
    ):
        owner = existing_category.user_id + 1

        category_repo_mock.get_by_id.return_value = existing_category

        with pytest.raises(PermissionException, match="You don't have permission to archive this category"):
            await category_service.archive_category(existing_category.id, owner)

        category_repo_mock.archive.assert_not_called()

    async def test_archive_category_archived_category(
            self,
            category_service: CategoryService,
            category_repo_mock: CategoryRepository,
    ):
        archived_category = Category(
            id=1,
            name="Foods",
            user_id=1,
            created_at=datetime.datetime(2026, 2, 10),
            archived_at=datetime.datetime(2020, 1, 1),
        )

        category_repo_mock.get_by_id.return_value = archived_category

        with pytest.raises(NotAllowedActionException, match="Category is archived"):
            await category_service.archive_category(archived_category.id, archived_category.user_id)

        category_repo_mock.archive.assert_not_called()


class TestRestoreCategory:
    async def test_restore_category_success(
            self,
            existing_category: Category,
            category_service: CategoryService,
            category_repo_mock: CategoryRepository,
    ):
        archived_category = Category(
            id=existing_category.id,
            name=existing_category.name,
            user_id=existing_category.user_id,
            created_at=existing_category.created_at,
            archived_at=datetime.datetime(2020, 1, 1),
        )

        category_repo_mock.get_by_id.return_value = archived_category
        category_repo_mock.restore.return_value = existing_category

        await category_service.restore_category(existing_category.id, existing_category.user_id)

        category_repo_mock.restore.assert_called_once()

    async def test_restore_category_not_found_category(
            self,
            existing_category: Category,
            category_service: CategoryService,
            category_repo_mock: CategoryRepository,
    ):
        category_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Category not found"):
            await category_service.restore_category(existing_category.id, existing_category.user_id)

        category_repo_mock.restore.assert_not_called()

    async def test_restore_category_wrong_owner(
            self,
            existing_category: Category,
            category_service: CategoryService,
            category_repo_mock: CategoryRepository,
    ):
        owner = existing_category.user_id + 1

        category_repo_mock.get_by_id.return_value = existing_category

        with pytest.raises(PermissionException, match="You don't have permission to restore this category"):
            await category_service.restore_category(existing_category.id, owner)

        category_repo_mock.restore.assert_not_called()

    async def test_restore_category_not_archived_category(
            self,
            category_service: CategoryService,
            category_repo_mock: CategoryRepository,
    ):
        not_archived_category = Category(
            id=1,
            name="Foods",
            user_id=1,
            created_at=datetime.datetime(2026, 2, 10),
            archived_at=None
        )

        category_repo_mock.get_by_id.return_value = not_archived_category

        with pytest.raises(NotAllowedActionException, match="Category is not archived"):
            await category_service.restore_category(not_archived_category.id, not_archived_category.user_id)

        category_repo_mock.restore.assert_not_called()

    async def test_restore_category_duplicated_active_category(
            self,
            existing_category: Category,
            category_service: CategoryService,
            category_repo_mock: CategoryRepository,
    ):
        category_repo_mock.get_by_user_and_name.return_value = existing_category
        archived_category = Category(
            id=existing_category.id + 1,
            name=existing_category.name,
            created_at=existing_category.created_at,
            user_id=existing_category.user_id,
            archived_at=datetime.datetime(2026, 2, 10),
        )

        category_repo_mock.get_by_id.return_value =archived_category

        with pytest.raises(ValueExistsException, match="Active category with this name already exists"):
            await category_service.restore_category(archived_category.id, archived_category.user_id)

        category_repo_mock.restore.assert_not_called()
