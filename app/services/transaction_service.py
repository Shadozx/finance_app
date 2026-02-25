from app.repositories import TransactionRepository, CurrencyRepository, CategoryRepository
from app.models import Transaction
from app.schemas import TransactionResponse, TransactionCreate, TransactionUpdate
from app.exception import NotFoundException, NotAllowedActionException


class TransactionService:
    def __init__(
            self,
            transaction_repository: TransactionRepository,
            category_repository: CategoryRepository,
            currency_repository: CurrencyRepository
    ):
        self.transaction_repository = transaction_repository
        self.category_repository = category_repository
        self.currency_repository = currency_repository

    async def create_transaction(self,
                                 user_id: int,
                                 data: TransactionCreate) -> TransactionResponse:

        await self.validate_category(user_id, data.category_id)

        await self.validate_currency(data.currency_code)

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

        return TransactionResponse.model_validate(created_transaction)

    async def get_transaction(
            self,
            transaction_id: int,
            user_id: int
    ) -> TransactionResponse:
        existing_transaction = await self.transaction_repository.get_by_id(transaction_id)

        await self.validate_transaction(user_id, existing_transaction)

        return TransactionResponse.model_validate(existing_transaction)

    async def get_user_transactions(
            self,
            user_id: int,
            limit: int = 20,
            offset: int = 0,
    ) -> list[TransactionResponse]:
        user_transactions = await self.transaction_repository.get_by_user(user_id, limit, offset)

        return [
            TransactionResponse.model_validate(tr) for tr in user_transactions
        ]

    async def update_transaction(
            self,
            transaction_id: int,
            user_id: int,
            data: TransactionUpdate
    ) -> TransactionResponse:

        existing_transaction = await self.transaction_repository.get_by_id(transaction_id)

        await self.validate_transaction(user_id, existing_transaction)

        await self.validate_category(user_id, data.category_id)

        await self.validate_currency(data.currency_code)

        existing_transaction.category_id = data.category_id
        existing_transaction.currency_code = data.currency_code
        existing_transaction.date = data.date
        existing_transaction.description = data.description
        existing_transaction.type = data.type
        existing_transaction.amount = data.amount

        updated_transaction = await self.transaction_repository.update(existing_transaction)

        return TransactionResponse.model_validate(updated_transaction)

    async def validate_category(
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
            raise PermissionError("You don't have permission to this category")

        if existing_category.archived_at:
            raise NotAllowedActionException("Archived category is no allowed to use")

    async def validate_currency(
            self,
            currency_code: str
    ) -> None:
        existing_currency = await self.currency_repository.get_by_code(currency_code)

        if not existing_currency:
            raise NotFoundException("Currency not found")

        if not existing_currency.is_active:
            raise NotAllowedActionException("Currency is not active")

    async def validate_transaction(
            self,
            user_id: int,
            transaction: Transaction | None
    ) -> None:
        if not transaction:
            raise NotFoundException("Transaction not found")

        if transaction.user_id != user_id:
            raise PermissionError("You don't have permission to this transaction")

    async def delete_transaction(
            self,
            transaction_id: int,
            user_id: int,
    ) -> None:
        existing_transaction = await self.transaction_repository.get_by_id(transaction_id)

        await self.validate_transaction(user_id, existing_transaction)

        await self.transaction_repository.delete(existing_transaction)
