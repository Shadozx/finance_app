import structlog

from app.core import UnitOfWork
from app.core.exceptions import ValueExistsException
from app.models import TransactionTemplate, TransactionTemplateSplit
from app.repositories import (
    CategoryRepository,
    CurrencyRepository,
    TransactionTemplateRepository,
    TransactionTemplateSplitRepository,
)
from app.schemas import (
    TransactionTemplateCreate,
    TransactionTemplateListItem,
    TransactionTemplateResponse,
    TransactionTemplateSplitResponse,
    TransactionTemplateUpdate,
)
from app.services import validators

logger = structlog.get_logger()


class TransactionTemplateService:
    def __init__(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        category_repository: CategoryRepository,
        currency_repository: CurrencyRepository,
        unit_of_work: UnitOfWork,
    ):
        self.transaction_template_repository = transaction_template_repository
        self.transaction_template_split_repository = transaction_template_split_repository
        self.category_repository = category_repository
        self.currency_repository = currency_repository
        self.unit_of_work = unit_of_work

    async def get_template(self, template_id: int, user_id: int) -> TransactionTemplateResponse:
        existing_template = await validators.validate_template(
            self.transaction_template_repository, user_id, template_id
        )

        splits = await self.transaction_template_split_repository.get_by_template(template_id)

        return self._to_response(existing_template, splits)

    async def get_user_templates(
        self, user_id: int, limit: int = 20, offset: int = 0
    ) -> list[TransactionTemplateListItem]:
        user_templates = await self.transaction_template_repository.get_by_user(
            user_id, limit, offset
        )

        template_ids = [template.id for template in user_templates]

        ids_with_splits: set[int] = set()

        if template_ids:
            ids_with_splits = (
                await self.transaction_template_split_repository.get_template_ids_with_splits(
                    template_ids
                )
            )

        return [
            self._to_list_item(template, template.id in ids_with_splits)
            for template in user_templates
        ]

    async def create_template(
        self, data: TransactionTemplateCreate, user_id: int
    ) -> TransactionTemplateResponse:

        if await self.transaction_template_repository.get_by_user_and_name(data.name, user_id):
            raise ValueExistsException("Transaction template with this name already exists")

        await validators.validate_category(self.category_repository, user_id, data.category_id)

        if data.splits is not None:
            split_category_ids = {
                split.category_id for split in data.splits if split.category_id is not None
            }

            for category_id in split_category_ids:
                await validators.validate_category(self.category_repository, user_id, category_id)

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

        splits: list[TransactionTemplateSplit] = []

        if data.splits is not None:
            splits = [
                TransactionTemplateSplit(
                    transaction_template_id=created_template.id,
                    category_id=split.category_id,
                    amount=split.amount,
                    description=split.description,
                )
                for split in data.splits
            ]

            await self.transaction_template_split_repository.add_all(splits)

        await self.unit_of_work.commit()

        logger.info(
            "transaction_template_create_success", user_id=user_id, template_id=created_template.id
        )

        return self._to_response(created_template, splits)

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

        currency_changed = data.currency_code != existing_template.currency_code

        # Unlike transactions, a template describes the future: an archived
        # category here would produce a transaction that cannot be created.
        await validators.validate_category(
            self.category_repository,
            user_id,
            data.category_id,
            allow_archived=False,
        )

        if data.splits is not None:
            split_category_ids = {
                split.category_id for split in data.splits if split.category_id is not None
            }

            for category_id in split_category_ids:
                await validators.validate_category(
                    self.category_repository,
                    user_id,
                    category_id,
                    allow_archived=False,
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

        old_splits = await self.transaction_template_split_repository.get_by_template(template_id)

        splits: list[TransactionTemplateSplit] = []

        if old_splits:
            await self.transaction_template_split_repository.delete_by_template(template_id)

        if data.splits is not None:
            splits = [
                TransactionTemplateSplit(
                    transaction_template_id=template_id,
                    category_id=split.category_id,
                    amount=split.amount,
                    description=split.description,
                )
                for split in data.splits
            ]

            await self.transaction_template_split_repository.add_all(splits)

        await self.unit_of_work.commit()

        logger.info(
            "transaction_template_update_success", user_id=user_id, template_id=updated_template.id
        )

        return self._to_response(updated_template, splits)

    async def delete_template(self, template_id: int, user_id: int) -> None:
        existing_template = await validators.validate_template(
            self.transaction_template_repository, user_id, template_id
        )

        await self.transaction_template_repository.delete(existing_template)

        await self.unit_of_work.commit()

        logger.info(
            "transaction_template_delete_success", user_id=user_id, template_id=existing_template.id
        )

    def _to_response(
        self,
        template: TransactionTemplate,
        splits: list[TransactionTemplateSplit] | None = None,
    ) -> TransactionTemplateResponse:
        response = TransactionTemplateResponse.model_validate(template)
        response.splits = (
            [TransactionTemplateSplitResponse.model_validate(split) for split in splits]
            if splits
            else None
        )
        response.has_splits = bool(splits)

        return response

    def _to_list_item(
        self, template: TransactionTemplate, has_splits: bool = False
    ) -> TransactionTemplateListItem:
        response = TransactionTemplateListItem.model_validate(template)
        response.has_splits = has_splits
        return response
