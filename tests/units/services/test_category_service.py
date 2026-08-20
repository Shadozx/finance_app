from datetime import datetime, timezone

import pytest

from app.core import UnitOfWork
from app.models import Category
from app.repositories import CategoryRepository
from app.services import CategoryService
from app.schemas import CategoryCreate, CategoryUpdate, CategoryResponse, CategoryStatus

from app.core.exceptions import (
    NotFoundException,
    ValueExistsException,
    NotAllowedActionException,
    PermissionException,
)
from tests.units.services.helpers import assert_model_fields, as_persisted, make_category


class TestCreateCategory:
    @pytest.fixture
    def data(self):
        return CategoryCreate(
            name="Salary",
        )

    async def test_create_category_success(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        data: CategoryCreate,
    ):
        user_id = 1

        category_repo_mock.get_by_user_and_name.return_value = None

        category_repo_mock.add.side_effect = as_persisted

        result = await category_service.create_category(data, user_id)

        call_args = category_repo_mock.add.call_args[0][0]

        assert result == CategoryResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            name=data.name,
            user_id=user_id,
        )

        category_repo_mock.get_by_user_and_name.assert_called_once_with(user_id, data.name)

        category_repo_mock.add.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_create_category_existing_category(
        self,
        category_service: CategoryService,
        unit_of_work_mock: UnitOfWork,
        category_repo_mock: CategoryRepository,
        existing_category: Category,
        data: CategoryCreate,
    ):
        data.name = existing_category.name
        user_id = existing_category.user_id

        category_repo_mock.get_by_user_and_name.return_value = existing_category

        with pytest.raises(ValueExistsException, match="Category with this name exists"):
            await category_service.create_category(data, user_id)

        category_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()


class TestUpdateCategory:
    @pytest.fixture
    def data(self):
        return CategoryUpdate(name="Salary")

    async def test_update_category_success(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_category: Category,
        data: CategoryUpdate,
    ):
        category_id = existing_category.id
        user_id = existing_category.user_id

        category_repo_mock.get_by_id.return_value = existing_category
        category_repo_mock.get_by_user_and_name.return_value = None

        category_repo_mock.update.side_effect = as_persisted

        result = await category_service.update_category(category_id, data, user_id)

        call_args = category_repo_mock.update.call_args[0][0]

        assert result == CategoryResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            name=data.name,
            user_id=user_id,
        )

        category_repo_mock.get_by_id.assert_called_once_with(category_id)

        category_repo_mock.get_by_user_and_name.assert_called_once_with(user_id, data.name)

        category_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_category_not_found_category(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        data: CategoryUpdate,
    ):
        category_id = 999
        user_id = 1

        category_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Category not found"):
            await category_service.update_category(category_id, data, user_id)

        category_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_category_wrong_owner(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_category: Category,
        data: CategoryUpdate,
    ):
        wrong_user_id = existing_category.user_id + 1

        category_repo_mock.get_by_id.return_value = existing_category

        with pytest.raises(
            PermissionException, match="You don't have permission to update this category"
        ):
            await category_service.update_category(existing_category.id, data, wrong_user_id)

        category_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_category_duplicated_name(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_category: Category,
        data: CategoryUpdate,
    ):
        category_repo_mock.get_by_id.return_value = existing_category

        duplicate_category = make_category(
            id=existing_category.id + 1,
            name="Salary",
            user_id=existing_category.user_id,
        )
        category_repo_mock.get_by_user_and_name.return_value = duplicate_category

        data.name = duplicate_category.name

        with pytest.raises(ValueExistsException, match="Category with this name exists"):
            await category_service.update_category(
                existing_category.id, data, existing_category.user_id
            )

        category_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()


class TestGetUserCategories:
    async def test_get_user_categories(
        self,
        category_repo_mock: CategoryRepository,
        category_service: CategoryService,
    ):
        user_id = 1

        user_categories = [
            make_category(
                id=1,
                name="Salary",
                user_id=user_id,
            ),
            make_category(
                id=2,
                name="Foods",
                user_id=user_id,
            ),
        ]

        category_repo_mock.get_by_user.return_value = user_categories

        result = await category_service.get_user_categories(user_id)

        assert result == [CategoryResponse.model_validate(c) for c in user_categories]

        category_repo_mock.get_by_user.assert_called_once_with(
            user_id=user_id,
            status=CategoryStatus.ACTIVE,
        )

    async def test_get_user_empty_categories(
        self,
        category_repo_mock: CategoryRepository,
        category_service: CategoryService,
    ):
        user_id = 1

        user_categories = []

        category_repo_mock.get_by_user.return_value = user_categories

        result = await category_service.get_user_categories(user_id)

        assert result == [CategoryResponse.model_validate(c) for c in user_categories]

        category_repo_mock.get_by_user.assert_called_once_with(
            user_id=user_id,
            status=CategoryStatus.ACTIVE,
        )


class TestArchiveCategory:
    async def test_archive_category_success(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_category: Category,
    ):
        category_repo_mock.get_by_id.return_value = existing_category

        await category_service.archive_category(existing_category.id, existing_category.user_id)

        category_repo_mock.get_by_id.assert_called_once_with(existing_category.id)

        category_repo_mock.archive.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_archive_category_not_found_category(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
    ):
        category_id = 999
        user_id = 1

        category_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Category not found"):
            await category_service.archive_category(category_id, user_id)

        category_repo_mock.archive.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_archive_category_wrong_owner(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_category: Category,
    ):
        wrong_user = existing_category.user_id + 1

        category_repo_mock.get_by_id.return_value = existing_category

        with pytest.raises(
            PermissionException, match="You don't have permission to archive this category"
        ):
            await category_service.archive_category(existing_category.id, wrong_user)

        category_repo_mock.archive.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_archive_category_archived_category(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_category: Category,
    ):
        category_id = existing_category.id
        user_id = existing_category.user_id

        existing_category.archived_at = datetime(2026, 5, 1)

        category_repo_mock.get_by_id.return_value = existing_category

        with pytest.raises(NotAllowedActionException, match="Category is archived"):
            await category_service.archive_category(category_id, user_id)

        category_repo_mock.archive.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()


class TestRestoreCategory:
    async def test_restore_category_success(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_category: Category,
    ):
        archived_category = make_category(
            id=existing_category.id,
            name=existing_category.name,
            user_id=existing_category.user_id,
            created_at=existing_category.created_at,
            archived_at=datetime(2026, 5, 1),
        )

        category_repo_mock.get_by_id.return_value = archived_category

        await category_service.restore_category(existing_category.id, existing_category.user_id)

        category_repo_mock.get_by_id.assert_called_once_with(existing_category.id)

        category_repo_mock.restore.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_restore_category_not_found_category(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
    ):
        category_id = 999
        user_id = 1

        category_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Category not found"):
            await category_service.restore_category(category_id, user_id)

        category_repo_mock.restore.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_restore_category_wrong_owner(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_category: Category,
    ):
        wrong_user_id = existing_category.user_id + 1

        category_repo_mock.get_by_id.return_value = existing_category

        with pytest.raises(
            PermissionException, match="You don't have permission to restore this category"
        ):
            await category_service.restore_category(existing_category.id, wrong_user_id)

        category_repo_mock.restore.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_restore_category_not_archived_category(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
    ):
        not_archived_category = make_category(name="Foods", archived_at=None)

        category_repo_mock.get_by_id.return_value = not_archived_category

        with pytest.raises(NotAllowedActionException, match="Category is not archived"):
            await category_service.restore_category(
                not_archived_category.id, not_archived_category.user_id
            )

        category_repo_mock.restore.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_restore_category_duplicated_active_category(
        self,
        category_service: CategoryService,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_category: Category,
    ):
        category_repo_mock.get_by_user_and_name.return_value = existing_category

        archived_category = make_category(
            id=existing_category.id + 1,
            name=existing_category.name,
            user_id=existing_category.user_id,
            archived_at=datetime(2026, 2, 10),
        )

        category_repo_mock.get_by_id.return_value = archived_category

        with pytest.raises(
            ValueExistsException, match="Active category with this name already exists"
        ):
            await category_service.restore_category(archived_category.id, archived_category.user_id)

        category_repo_mock.restore.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()
