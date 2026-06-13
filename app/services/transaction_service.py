import structlog

from app.repositories import (
    TransactionRepository,
    CurrencyRepository,
    CategoryRepository,
    TransactionTemplateRepository
)
from app.models import Transaction
from app.schemas import (
    TransactionResponse,
    TransactionCreate,
    TransactionUpdate,
    TransactionFilters,
    UseTemplateRequest
)
from app.services import validators

logger = structlog.get_logger()


class TransactionService:
    def __init__(
            self,
            transaction_repository: TransactionRepository,
            transaction_template_repository: TransactionTemplateRepository,
            category_repository: CategoryRepository,
            currency_repository: CurrencyRepository
    ):
        self.transaction_repository = transaction_repository
        self.transaction_template_repository = transaction_template_repository
        self.category_repository = category_repository
        self.currency_repository = currency_repository

    async def create_transaction(
            self,
            data: TransactionCreate,
            user_id: int) -> TransactionResponse:
        await validators.validate_category(self.category_repository, user_id, data.category_id)

        await validators.validate_currency(self.currency_repository, data.currency_code)

        new_transaction = Transaction(
            type=data.type,
            amount=data.amount,
            description=data.description,
            user_id=user_id,
            category_id=data.category_id,
            currency_code=data.currency_code,
            date=data.date,
        )

        created_transaction = await self.transaction_repository.create(new_transaction)

        logger.info("transaction_create_success", user_id=user_id, transaction_id=created_transaction.id)

        return TransactionResponse.model_validate(created_transaction)

    async def create_transaction_from_template(
            self,
            template_id: int,
            data: UseTemplateRequest,
            user_id: int,
    ) -> TransactionResponse:
        existing_template = await validators.validate_template(
            self.transaction_template_repository,
            user_id,
            template_id
        )

        final_type = (
            data.type
            if data.type is not None
            else existing_template.type
        )
        final_amount = (
            data.amount
            if data.amount is not None
            else existing_template.amount
        )
        final_category_id = (
            data.category_id
            if data.category_id is not None
            else existing_template.category_id
        )
        final_currency_code = (
            data.currency_code
            if data.currency_code is not None
            else existing_template.currency_code
        )
        final_description = (
            data.description
            if data.description is not None
            else existing_template.description
        )

        await validators.validate_category(self.category_repository, user_id, final_category_id)
        await validators.validate_currency(self.currency_repository, final_currency_code)

        new_transaction = Transaction(
            type=final_type,
            amount=final_amount,
            description=final_description,
            currency_code=final_currency_code,
            user_id=user_id,
            category_id=final_category_id,
            date=data.date,
        )

        created_transaction = await self.transaction_repository.create(new_transaction)

        logger.info("transaction_create_from_template_success", user_id=user_id, transaction_id=created_transaction.id)

        return TransactionResponse.model_validate(created_transaction)

    async def get_transaction(
            self,
            transaction_id: int,
            user_id: int
    ) -> TransactionResponse:
        existing_transaction = await validators.validate_transaction(
            self.transaction_repository,
            user_id,
            transaction_id
        )

        return TransactionResponse.model_validate(existing_transaction)

    async def get_user_transactions(
            self,
            user_id: int,
            filters: TransactionFilters,
            limit: int = 20,
            offset: int = 0,
    ) -> list[TransactionResponse]:
        user_transactions = await self.transaction_repository.get_by_user(user_id, filters, limit, offset)

        return [
            TransactionResponse.model_validate(tr) for tr in user_transactions
        ]

    async def update_transaction(
            self,
            transaction_id: int,
            data: TransactionUpdate,
            user_id: int,
    ) -> TransactionResponse:
        existing_transaction = await validators.validate_transaction(
            self.transaction_repository,
            user_id,
            transaction_id
        )

        await validators.validate_category(self.category_repository, user_id, data.category_id)

        await validators.validate_currency(self.currency_repository, data.currency_code)

        existing_transaction.category_id = data.category_id
        existing_transaction.currency_code = data.currency_code
        existing_transaction.date = data.date
        existing_transaction.description = data.description
        existing_transaction.type = data.type
        existing_transaction.amount = data.amount

        updated_transaction = await self.transaction_repository.update(existing_transaction)

        logger.info("transaction_update_success", user_id=user_id, transaction_id=updated_transaction.id)

        return TransactionResponse.model_validate(updated_transaction)

    async def delete_transaction(
            self,
            transaction_id: int,
            user_id: int,
    ) -> None:
        existing_transaction = await validators.validate_transaction(
            self.transaction_repository,
            user_id,
            transaction_id
        )

        await self.transaction_repository.delete(existing_transaction)

        logger.info("transaction_delete_success", user_id=user_id, transaction_id=transaction_id)
