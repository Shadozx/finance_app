from app.models import Category
from app.repositories import CategoryRepository
from app.schemas import CategoryResponse, CategoryCreate, CategoryUpdate
from app.exception import ValueExistsException, NotFoundException, NotAllowedActionException


class CategoryService:

    def __init__(self, category_repository: CategoryRepository):
        self.category_repository = category_repository

    async def create_category(
            self,
            user_id: int,
            data: CategoryCreate
    ) -> CategoryResponse:
        if await self.category_repository.get_by_user_and_name(user_id, data.name):
            raise ValueExistsException("User has category with this name")

        new_category = Category(
            name=data.name,
            user_id=user_id,
        )

        created_category = await self.category_repository.create(new_category)

        return CategoryResponse.model_validate(created_category)

    async def get_user_categories(self, user_id: int) -> list[CategoryResponse]:
        categories = await self.category_repository.get_by_user(user_id)
        return [CategoryResponse.model_validate(cat) for cat in categories]

    async def update_category(
            self,
            category_id: int,
            user_id: int,
            data: CategoryUpdate
    ) -> CategoryResponse:
        existing_category = await self.category_repository.get_by_id(category_id)

        if existing_category is None:
            raise NotFoundException("Category not found")

        if user_id != existing_category.user_id:
            raise PermissionError("You don't have permission to update this category")

        duplicate = await self.category_repository.get_by_user_and_name(user_id, data.name)

        if duplicate and duplicate.id != category_id:
            raise ValueExistsException("User has category with this name")

        existing_category.name = data.name

        updated_category = await self.category_repository.update(existing_category)

        return CategoryResponse.model_validate(updated_category)

    async def archive_category(
            self,
            category_id: int,
            user_id: int
    ) -> None:
        existing_category = await self.category_repository.get_by_id(category_id)

        if existing_category is None:
            raise NotFoundException("Category not found")

        if user_id != existing_category.user_id:
            raise PermissionError("You don't have permission to update this category")

        await self.category_repository.archive(existing_category)

    async def restore_category(
            self,
            category_id: int,
            user_id: int
    ) -> CategoryResponse:
        existing_category = await self.category_repository.get_by_id(category_id)

        if not existing_category:
            raise NotFoundException("Category not found")

        if existing_category.user_id != user_id:
            raise PermissionError("You don't have permission to restore this category")

        if not existing_category.archived_at:
            raise NotAllowedActionException("Category is not archived")

        duplicate = await self.category_repository.get_by_user_and_name(
            user_id,
            existing_category.name
        )

        if duplicate and duplicate.id != category_id and duplicate.archived_at is None:
            raise ValueExistsException(
                f"Cannot restore: active category '{existing_category.name}' already exists"
            )

        await self.category_repository.restore(existing_category)
        return CategoryResponse.model_validate(existing_category)

