import structlog

from app.core import UnitOfWork
from app.core.exceptions import NotAllowedActionException
from app.models import Transaction, TransactionKind, TransactionSplit
from app.repositories import (
    AccountRepository,
    CategoryRepository,
    CurrencyRepository,
    TransactionRepository,
    TransactionSplitRepository,
    TransactionTemplateRepository,
)
from app.schemas import (
    TransactionCreate,
    TransactionFilters,
    TransactionListItem,
    TransactionResponse,
    TransactionSplitResponse,
    TransactionUpdate,
    UseTemplateRequest,
)
from app.services import validators

logger = structlog.get_logger()


class TransactionService:
    def __init__(
        self,
        transaction_repository: TransactionRepository,
        transaction_split_repository: TransactionSplitRepository,
        transaction_template_repository: TransactionTemplateRepository,
        account_repository: AccountRepository,
        category_repository: CategoryRepository,
        currency_repository: CurrencyRepository,
        unit_of_work: UnitOfWork,
    ):
        self.transaction_repository = transaction_repository
        self.transaction_split_repository = transaction_split_repository
        self.transaction_template_repository = transaction_template_repository
        self.account_repository = account_repository
        self.category_repository = category_repository
        self.currency_repository = currency_repository
        self.unit_of_work = unit_of_work

    async def create_transaction(
        self, data: TransactionCreate, user_id: int
    ) -> TransactionResponse:
        await validators.validate_category(self.category_repository, user_id, data.category_id)

        if data.splits is not None:
            split_category_ids = {
                split.category_id for split in data.splits if split.category_id is not None
            }

            for category_id in split_category_ids:
                await validators.validate_category(self.category_repository, user_id, category_id)

        await validators.validate_currency(self.currency_repository, data.currency_code)

        account = await validators.validate_account(
            self.account_repository, user_id, data.account_id
        )

        settled_amount = validators.resolve_settled_amount(
            account, data.currency_code, data.amount, data.settled_amount
        )

        new_transaction = Transaction(
            type=data.type,
            kind=TransactionKind.REGULAR,
            amount=data.amount,
            settled_amount=settled_amount,
            settled_currency_code=account.currency_code,
            description=data.description,
            account_id=data.account_id,
            user_id=user_id,
            category_id=data.category_id,
            currency_code=data.currency_code,
            date=data.date,
        )

        created_transaction = await self.transaction_repository.add(new_transaction)

        splits: list[TransactionSplit] = []

        if data.splits is not None:
            settled_amounts = validators.resolve_splits(data.amount, settled_amount, data.splits)

            splits = [
                TransactionSplit(
                    transaction_id=created_transaction.id,
                    category_id=split.category_id,
                    amount=split.amount,
                    settled_amount=split_settled,
                    description=split.description,
                )
                for split, split_settled in zip(data.splits, settled_amounts, strict=True)
            ]

            await self.transaction_split_repository.add_all(splits)

        await self.unit_of_work.commit()

        logger.info(
            "transaction_create_success", user_id=user_id, transaction_id=created_transaction.id
        )

        return self._to_response(created_transaction, splits=splits)

    async def create_transaction_from_template(
        self,
        template_id: int,
        data: UseTemplateRequest,
        user_id: int,
    ) -> TransactionResponse:
        existing_template = await validators.validate_template(
            self.transaction_template_repository, user_id, template_id
        )

        final_type = data.type if data.type is not None else existing_template.type
        final_amount = data.amount if data.amount is not None else existing_template.amount
        final_category_id = (
            data.category_id if data.category_id is not None else existing_template.category_id
        )
        final_currency_code = (
            data.currency_code
            if data.currency_code is not None
            else existing_template.currency_code
        )
        final_description = (
            data.description if data.description is not None else existing_template.description
        )

        await validators.validate_category(self.category_repository, user_id, final_category_id)
        await validators.validate_currency(self.currency_repository, final_currency_code)

        account = await validators.validate_account(
            self.account_repository, user_id, data.account_id
        )

        settled_amount = validators.resolve_settled_amount(
            account, final_currency_code, final_amount, data.settled_amount
        )

        new_transaction = Transaction(
            type=final_type,
            kind=TransactionKind.REGULAR,
            amount=final_amount,
            description=final_description,
            currency_code=final_currency_code,
            settled_amount=settled_amount,
            settled_currency_code=account.currency_code,
            account_id=data.account_id,
            user_id=user_id,
            category_id=final_category_id,
            date=data.date,
        )

        created_transaction = await self.transaction_repository.add(new_transaction)

        await self.unit_of_work.commit()

        logger.info(
            "transaction_create_from_template_success",
            user_id=user_id,
            transaction_id=created_transaction.id,
        )

        return self._to_response(created_transaction)

    async def get_transaction(self, transaction_id: int, user_id: int) -> TransactionResponse:
        existing_transaction = await validators.validate_transaction(
            self.transaction_repository, user_id, transaction_id
        )

        counterpart_account_id = None

        if existing_transaction.transfer_group_id is not None:
            counterparts = await self.transaction_repository.get_counterpart_account_ids(
                [existing_transaction.transfer_group_id], user_id
            )
            counterpart_account_id = counterparts.get(existing_transaction.id)

        splits = await self.transaction_split_repository.get_by_transaction(transaction_id)

        return self._to_response(existing_transaction, counterpart_account_id, splits)

    async def get_user_transactions(
        self,
        user_id: int,
        filters: TransactionFilters,
        limit: int = 20,
        offset: int = 0,
    ) -> list[TransactionListItem]:
        transactions = await self.transaction_repository.get_by_user(
            user_id, filters, limit, offset
        )

        group_ids = [
            transaction.transfer_group_id
            for transaction in transactions
            if transaction.transfer_group_id is not None
        ]

        counterparts: dict[int, int] = {}

        if group_ids:
            counterparts = await self.transaction_repository.get_counterpart_account_ids(
                group_ids, user_id
            )

        transaction_ids = [transaction.id for transaction in transactions]

        ids_with_splits: set[int] = set()

        if transaction_ids:
            ids_with_splits = (
                await self.transaction_split_repository.get_transaction_ids_with_splits(
                    transaction_ids
                )
            )

        return [
            self._to_list_item(
                transaction,
                counterparts.get(transaction.id),
                transaction.id in ids_with_splits,
            )
            for transaction in transactions
        ]

    async def update_transaction(
        self,
        transaction_id: int,
        data: TransactionUpdate,
        user_id: int,
    ) -> TransactionResponse:
        existing_transaction = await validators.validate_transaction(
            self.transaction_repository, user_id, transaction_id
        )

        if existing_transaction.kind == TransactionKind.TRANSFER:
            raise NotAllowedActionException("Transfer cannot be edited one side at a time")

        category_changed = data.category_id != existing_transaction.category_id
        currency_changed = data.currency_code != existing_transaction.currency_code
        account_changed = data.account_id != existing_transaction.account_id

        await validators.validate_category(
            self.category_repository,
            user_id,
            data.category_id,
            allow_archived=not category_changed,
        )

        old_splits = await self.transaction_split_repository.get_by_transaction(transaction_id)

        if data.splits is not None:
            old_category_ids = {
                split.category_id for split in old_splits if split.category_id is not None
            }
            new_category_ids = {
                split.category_id for split in data.splits if split.category_id is not None
            }

            for category_id in new_category_ids:
                # A category already used by this transaction stays allowed even
                # if archived later; attaching a new archived one is not.
                await validators.validate_category(
                    self.category_repository,
                    user_id,
                    category_id,
                    allow_archived=category_id in old_category_ids,
                )

        await validators.validate_currency(
            self.currency_repository,
            data.currency_code,
            allow_inactive=not currency_changed,
        )

        account = await validators.validate_account(
            self.account_repository,
            user_id,
            data.account_id,
            allow_archived=not account_changed,
        )

        settled_amount = validators.resolve_settled_amount(
            account, data.currency_code, data.amount, data.settled_amount
        )

        existing_transaction.category_id = data.category_id
        existing_transaction.currency_code = data.currency_code
        existing_transaction.date = data.date
        existing_transaction.description = data.description
        existing_transaction.type = data.type
        existing_transaction.amount = data.amount
        existing_transaction.account_id = data.account_id
        existing_transaction.settled_amount = settled_amount
        existing_transaction.settled_currency_code = account.currency_code

        updated_transaction = await self.transaction_repository.update(existing_transaction)

        splits: list[TransactionSplit] = []

        if old_splits:
            await self.transaction_split_repository.delete_by_transaction(transaction_id)

        if data.splits is not None:
            settled_amounts = validators.resolve_splits(data.amount, settled_amount, data.splits)

            splits = [
                TransactionSplit(
                    transaction_id=transaction_id,
                    category_id=split.category_id,
                    amount=split.amount,
                    settled_amount=split_settled,
                    description=split.description,
                )
                for split, split_settled in zip(data.splits, settled_amounts, strict=True)
            ]

            await self.transaction_split_repository.add_all(splits)

        await self.unit_of_work.commit()

        logger.info(
            "transaction_update_success", user_id=user_id, transaction_id=updated_transaction.id
        )

        return self._to_response(updated_transaction, splits=splits)

    async def delete_transaction(
        self,
        transaction_id: int,
        user_id: int,
    ) -> None:
        existing_transaction = await validators.validate_transaction(
            self.transaction_repository, user_id, transaction_id
        )

        if (
            existing_transaction.kind == TransactionKind.TRANSFER
            and existing_transaction.transfer_group_id is not None
        ):
            await self.transaction_repository.delete_by_transfer_group(
                existing_transaction.transfer_group_id,
                user_id,
            )

            await self.unit_of_work.commit()

            logger.info(
                "transfer_delete_via_transaction_success",
                user_id=user_id,
                transaction_id=transaction_id,
                transfer_group_id=str(existing_transaction.transfer_group_id),
            )
        else:
            await self.transaction_repository.delete(existing_transaction)

            await self.unit_of_work.commit()

            logger.info(
                "transaction_delete_success", user_id=user_id, transaction_id=transaction_id
            )

    def _to_list_item(
        self,
        transaction: Transaction,
        counterpart_account_id: int | None = None,
        has_splits: bool = False,
    ) -> TransactionListItem:
        response = TransactionListItem.model_validate(transaction)
        response.counterpart_account_id = counterpart_account_id
        response.has_splits = has_splits

        return response

    def _to_response(
        self,
        transaction: Transaction,
        counterpart_account_id: int | None = None,
        splits: list[TransactionSplit] | None = None,
    ) -> TransactionResponse:
        response = TransactionResponse.model_validate(transaction)
        response.counterpart_account_id = counterpart_account_id
        response.splits = (
            [TransactionSplitResponse.model_validate(split) for split in splits] if splits else None
        )
        response.has_splits = bool(splits)

        return response
