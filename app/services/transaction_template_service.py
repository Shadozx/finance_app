import structlog

from app.core import UnitOfWork
from app.repositories import TransactionTemplateRepository, CategoryRepository, CurrencyRepository
from app.schemas import (
    TransactionTemplateCreate,
    TransactionTemplateUpdate,
    TransactionTemplateResponse,
)
from app.models import TransactionTemplate
from app.core.exceptions import ValueExistsException
from app.services import validators

logger = structlog.get_logger()


class TransactionTemplateService:
    def __init__(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        category_repository: CategoryRepository,
        currency_repository: CurrencyRepository,
        unit_of_work: UnitOfWork,
    ):
        self.transaction_template_repository = transaction_template_repository
        self.category_repository = category_repository
        self.currency_repository = currency_repository
        self.unit_of_work = unit_of_work

    async def get_template(self, template_id: int, user_id: int) -> TransactionTemplateResponse:
        existing_template = await validators.validate_template(
            self.transaction_template_repository, user_id, template_id
        )

        return TransactionTemplateResponse.model_validate(existing_template)

    async def get_user_templates(
        self, user_id: int, limit: int = 20, offset: int = 0
    ) -> list[TransactionTemplateResponse]:
        user_templates = await self.transaction_template_repository.get_by_user(
            user_id, limit, offset
        )

        return [TransactionTemplateResponse.model_validate(t) for t in user_templates]

    async def create_template(
        self, data: TransactionTemplateCreate, user_id: int
    ) -> TransactionTemplateResponse:

        if await self.transaction_template_repository.get_by_user_and_name(data.name, user_id):
            raise ValueExistsException("Transaction template with this name already exists")

        await validators.validate_category(self.category_repository, user_id, data.category_id)

        await validators.validate_currency(self.currency_repository, data.currency_code)

        new_template = TransactionTemplate(
            type=data.type,
            amount=data.amount,
            name=data.name,
            description=data.description,
            category_id=data.category_id,
            currency_code=data.currency_code,
            user_id=user_id,
        )

        created_template = await self.transaction_template_repository.add(new_template)

        await self.unit_of_work.commit()

        logger.info(
            "transaction_template_create_success", user_id=user_id, template_id=created_template.id
        )

        return TransactionTemplateResponse.model_validate(created_template)

    async def update_template(
        self, template_id: int, data: TransactionTemplateUpdate, user_id: int
    ) -> TransactionTemplateResponse:
        duplicate_template = await self.transaction_template_repository.get_by_user_and_name(
            data.name, user_id
        )

        if duplicate_template and duplicate_template.id != template_id:
            raise ValueExistsException("Transaction template with this name already exists")

        existing_template = await validators.validate_template(
            self.transaction_template_repository, user_id, template_id
        )

        category_changed = data.category_id != existing_template.category_id
        currency_changed = data.currency_code != existing_template.currency_code

        await validators.validate_category(
            self.category_repository,
            user_id,
            data.category_id,
            allow_archived=not category_changed,
        )

        await validators.validate_currency(
            self.currency_repository,
            data.currency_code,
            allow_inactive=not currency_changed,
        )

        existing_template.type = data.type
        existing_template.amount = data.amount
        existing_template.name = data.name
        existing_template.description = data.description
        existing_template.currency_code = data.currency_code
        existing_template.category_id = data.category_id

        updated_template = await self.transaction_template_repository.update(existing_template)

        await self.unit_of_work.commit()

        logger.info(
            "transaction_template_update_success", user_id=user_id, template_id=updated_template.id
        )

        return TransactionTemplateResponse.model_validate(updated_template)

    async def delete_template(self, template_id: int, user_id: int) -> None:
        existing_template = await validators.validate_template(
            self.transaction_template_repository, user_id, template_id
        )

        await self.transaction_template_repository.delete(existing_template)

        await self.unit_of_work.commit()

        logger.info(
            "transaction_template_delete_success", user_id=user_id, template_id=existing_template.id
        )
