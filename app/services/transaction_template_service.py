from app.repositories import TransactionTemplateRepository, CategoryRepository, CurrencyRepository
from app.schemas import TransactionTemplateCreate, TransactionTemplateUpdate, TransactionTemplateResponse
from app.models import TransactionTemplate
from app.core.exceptions import NotFoundException, PermissionException, NotAllowedActionException, ValueExistsException


class TransactionTemplateService:
    def __init__(
            self,
            template_repository: TransactionTemplateRepository,
            category_repository: CategoryRepository,
            currency_repository: CurrencyRepository,
    ):
        self.template_repository = template_repository
        self.category_repository = category_repository
        self.currency_repository = currency_repository

    async def get_template(
            self,
            template_id: int,
            user_id: int
    ) -> TransactionTemplateResponse:
        existing_template = await self.template_repository.get_by_id(template_id)

        await self._validate_template(user_id, existing_template)

        return TransactionTemplateResponse.model_validate(existing_template)

    async def get_user_templates(
            self,
            user_id: int,
            limit: int = 20,
            offset: int = 0
    ) -> list[TransactionTemplateResponse]:
        user_templates = await self.template_repository.get_by_user(user_id, limit, offset)

        return [
            TransactionTemplateResponse.model_validate(t) for t in user_templates
        ]

    async def create_template(
            self,
            data: TransactionTemplateCreate,
            user_id: int
    ) -> TransactionTemplateResponse:

        if await self.template_repository.get_by_user_and_name(data.name, user_id):
            raise ValueExistsException("Transaction template with this name already exists")

        await self._validate_category(user_id, data.category_id)

        await self._validate_currency(data.currency_code)

        new_template = TransactionTemplate(
            type=data.type,
            amount=data.amount,
            name=data.name,
            description=data.description,
            category_id=data.category_id,
            currency_code=data.currency_code,
            user_id=user_id
        )

        created_template = await self.template_repository.create(new_template)

        return TransactionTemplateResponse.model_validate(created_template)

    async def update_template(
            self,
            template_id: int,
            data: TransactionTemplateUpdate,
            user_id: int
    ) -> TransactionTemplateResponse:
        duplicate_template = await self.template_repository.get_by_user_and_name(data.name, user_id)

        if duplicate_template and duplicate_template.id != template_id:
            raise ValueExistsException("Transaction template with this name already exists")

        existing_template = await self.template_repository.get_by_id(template_id)

        await self._validate_template(user_id, existing_template)

        await self._validate_category(user_id, data.category_id)

        await self._validate_currency(data.currency_code)

        existing_template.type = data.type
        existing_template.amount = data.amount
        existing_template.name = data.name
        existing_template.description = data.description
        existing_template.currency_code = data.currency_code
        existing_template.category_id = data.category_id

        updated_template = await self.template_repository.update(existing_template)

        return TransactionTemplateResponse.model_validate(updated_template)

    async def delete_template(
            self,
            template_id: int,
            user_id: int
    ) -> None:
        existing_template = await self.template_repository.get_by_id(template_id)

        await self._validate_template(user_id, existing_template)

        await self.template_repository.delete(existing_template)

    async def _validate_category(
            self,
            user_id: int,
            category_id: int | None
    ) -> None:
        if not category_id:
            return

        existing_category = await self.category_repository.get_by_id(category_id)

        if not existing_category:
            raise NotFoundException("Category not found")

        if existing_category.user_id != user_id:
            raise PermissionException("You don't have permission to this category")

        if existing_category.archived_at:
            raise NotAllowedActionException("Archived category is not allowed to use")

    async def _validate_currency(
            self,
            currency_code: str
    ) -> None:
        existing_currency = await self.currency_repository.get_by_code(currency_code)

        if not existing_currency:
            raise NotFoundException("Currency not found")

        if not existing_currency.is_active:
            raise NotAllowedActionException("Currency is not active")

    async def _validate_template(
            self,
            user_id: int,
            template: TransactionTemplate | None
    ) -> None:
        if not template:
            raise NotFoundException("Transaction template not found")

        if template.user_id != user_id:
            raise PermissionException("You don't have permission to this transaction template")
