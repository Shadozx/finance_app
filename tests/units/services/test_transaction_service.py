import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pytest_mock import MockerFixture

from app.core import UnitOfWork
from app.core.exceptions import NotAllowedActionException, NotFoundException
from app.models import (
    Account,
    Category,
    Currency,
    Transaction,
    TransactionKind,
    TransactionSplit,
    TransactionType,
)
from app.repositories import (
    AccountRepository,
    CategoryRepository,
    CurrencyRepository,
    TransactionRepository,
    TransactionSplitRepository,
)
from app.schemas import (
    TransactionCreate,
    TransactionFilters,
    TransactionListItem,
    TransactionResponse,
    TransactionSplitCreate,
    TransactionUpdate,
)
from app.services import TransactionService, validators
from tests.units.services.helpers import (
    as_persisted,
    as_persisted_all,
    assert_model_fields,
    make_transaction,
)


class TestGetTransaction:
    async def test_get_transaction_success(
        self,
        mocker: MockerFixture,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        existing_transaction: Transaction,
    ):
        user_id = existing_transaction.user_id
        transaction_id = existing_transaction.id

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        transaction_split_repo_mock.get_by_transaction.return_value = []

        validate_transaction_spy = mocker.spy(validators, "validate_transaction")

        result = await transaction_service.get_transaction(transaction_id, user_id)

        assert result == TransactionResponse.model_validate(existing_transaction)

        validate_transaction_spy.assert_called_once_with(
            transaction_service.transaction_repository, user_id, transaction_id
        )

        transaction_repo_mock.get_by_id.assert_called_once()

        transaction_split_repo_mock.get_by_transaction.assert_called_once()

    async def test_get_transaction_not_found_transaction(
        self, transaction_service: TransactionService, transaction_repo_mock: TransactionRepository
    ):
        user_id = 1
        transaction_id = 999

        transaction_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Transaction not found"):
            await transaction_service.get_transaction(transaction_id, user_id)

        transaction_repo_mock.get_by_id.assert_called_once()

    async def test_get_transaction_transfer_includes_counterpart(
        self,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        existing_transaction: Transaction,
    ):
        group_id = uuid.uuid4()
        existing_transaction.kind = TransactionKind.TRANSFER
        existing_transaction.transfer_group_id = group_id

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        transaction_repo_mock.get_counterpart_account_ids.return_value = {
            existing_transaction.id: 777
        }
        transaction_split_repo_mock.get_by_transaction.return_value = []

        result = await transaction_service.get_transaction(
            existing_transaction.id,
            existing_transaction.user_id,
        )

        assert result.counterpart_account_id == 777

        transaction_repo_mock.get_counterpart_account_ids.assert_called_once_with(
            [group_id],
            existing_transaction.user_id,
        )


class TestDeleteTransaction:
    async def test_delete_transaction_success(
        self,
        mocker: MockerFixture,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
    ):
        user_id = existing_transaction.user_id
        transaction_id = existing_transaction.id

        transaction_repo_mock.get_by_id.return_value = existing_transaction

        validate_transaction_spy = mocker.spy(validators, "validate_transaction")

        await transaction_service.delete_transaction(transaction_id, user_id)

        validate_transaction_spy.assert_called_once_with(
            transaction_service.transaction_repository, user_id, transaction_id
        )

        transaction_repo_mock.get_by_id.assert_called_once()

        transaction_repo_mock.delete.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_delete_transaction_not_found(
        self,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        unit_of_work_mock: UnitOfWork,
    ):
        user_id = 1
        transaction_id = 999

        transaction_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Transaction not found"):
            await transaction_service.delete_transaction(transaction_id, user_id)

        transaction_repo_mock.get_by_id.assert_called_once()

        transaction_repo_mock.delete.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_delete_transaction_transfer_removes_whole_group(
        self,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
    ):
        group_id = uuid.uuid4()
        existing_transaction.kind = TransactionKind.TRANSFER
        existing_transaction.transfer_group_id = group_id

        transaction_repo_mock.get_by_id.return_value = existing_transaction

        await transaction_service.delete_transaction(
            existing_transaction.id,
            existing_transaction.user_id,
        )

        transaction_repo_mock.delete_by_transfer_group.assert_called_once_with(
            group_id,
            existing_transaction.user_id,
        )

        transaction_repo_mock.delete.assert_not_called()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_delete_transaction_regular_does_not_touch_transfer_group(
        self,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
    ):
        transaction_repo_mock.get_by_id.return_value = existing_transaction

        await transaction_service.delete_transaction(
            existing_transaction.id,
            existing_transaction.user_id,
        )

        transaction_repo_mock.delete.assert_called_once()

        transaction_repo_mock.delete_by_transfer_group.assert_not_called()

        unit_of_work_mock.commit.assert_awaited_once()


class TestCreateTransaction:
    @pytest.fixture
    def data(
        self,
        existing_transaction: Transaction,
        existing_currency: Currency,
        existing_account: Account,
    ):
        return TransactionCreate(
            type=existing_transaction.type,
            amount=existing_transaction.amount,
            currency_code=existing_transaction.currency_code,
            description=existing_transaction.description,
            date=existing_transaction.date,
            account_id=existing_transaction.account_id,
        )

    async def test_create_transaction_success(
        self,
        mocker: MockerFixture,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionCreate,
    ):
        user_id = existing_category.user_id
        data.category_id = existing_category.id

        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = existing_category
        account_repo_mock.get_by_id.return_value = existing_account

        transaction_repo_mock.add.side_effect = as_persisted
        transaction_split_repo_mock.add_all.side_effect = as_persisted_all

        validate_category_spy = mocker.spy(validators, "validate_category")
        validate_currency_spy = mocker.spy(validators, "validate_currency")
        validate_account_spy = mocker.spy(validators, "validate_account")
        resolve_settled_amount_spy = mocker.spy(validators, "resolve_settled_amount")

        result = await transaction_service.create_transaction(data, user_id)

        call_args = transaction_repo_mock.add.call_args[0][0]

        assert result == TransactionResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            amount=data.amount,
            type=data.type,
            kind=TransactionKind.REGULAR,
            user_id=user_id,
            category_id=data.category_id,
            currency_code=data.currency_code,
            settled_amount=data.amount,
            settled_currency_code=existing_account.currency_code,
            date=data.date,
        )

        validate_category_spy.assert_called_once_with(
            transaction_service.category_repository, user_id, existing_category.id
        )
        validate_currency_spy.assert_called_once_with(
            transaction_service.currency_repository, existing_currency.code
        )

        validate_account_spy.assert_called_once_with(
            transaction_service.account_repository, user_id, existing_account.id
        )

        resolve_settled_amount_spy.assert_called_once_with(
            existing_account,
            data.currency_code,
            data.amount,
            data.settled_amount,
        )

        transaction_repo_mock.add.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_create_transaction_without_category(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_currency: Currency,
        data: TransactionCreate,
    ):
        data.category_id = None
        user_id = 1

        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = None
        account_repo_mock.get_by_id.return_value = existing_account

        transaction_repo_mock.add.side_effect = as_persisted

        result = await transaction_service.create_transaction(data, user_id)

        call_args = transaction_repo_mock.add.call_args[0][0]

        assert result == TransactionResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            amount=data.amount,
            type=data.type,
            kind=TransactionKind.REGULAR,
            category_id=data.category_id,
            settled_amount=data.amount,
            settled_currency_code=existing_account.currency_code,
            user_id=user_id,
            date=data.date,
        )

        currency_repo_mock.get_by_code.assert_called_once()

        category_repo_mock.get_by_id.assert_not_called()

        transaction_repo_mock.add.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_create_transaction_different_currency_success(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_usd_currency: Currency,
        data: TransactionCreate,
    ):
        """A USD purchase on a UAH card: the account is charged in UAH."""
        data.category_id = None
        data.currency_code = existing_usd_currency.code
        data.amount = Decimal("24.00")
        data.settled_amount = Decimal("1000.00")

        user_id = existing_account.user_id

        currency_repo_mock.get_by_code.return_value = existing_usd_currency
        account_repo_mock.get_by_id.return_value = existing_account

        transaction_repo_mock.add.side_effect = as_persisted

        result = await transaction_service.create_transaction(data, user_id)

        call_args = transaction_repo_mock.add.call_args[0][0]

        assert result == TransactionResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            amount=data.amount,
            currency_code=existing_usd_currency.code,
            settled_amount=data.settled_amount,
            settled_currency_code=existing_account.currency_code,
        )

        transaction_repo_mock.add.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_create_transaction_different_currency_without_settled_amount(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_usd_currency: Currency,
        data: TransactionCreate,
    ):
        data.category_id = None
        data.currency_code = existing_usd_currency.code
        data.amount = Decimal("24.00")

        currency_repo_mock.get_by_code.return_value = existing_usd_currency
        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(
            NotAllowedActionException,
            match="Amount charged to the account is required, in the account currency",
        ):
            await transaction_service.create_transaction(data, existing_account.user_id)

        transaction_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_transaction_archived_category(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_category: Category,
        data: TransactionCreate,
    ):
        data.category_id = existing_category.id
        user_id = 1
        existing_category.archived_at = datetime.now(UTC)

        category_repo_mock.get_by_id.return_value = existing_category
        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(
            NotAllowedActionException, match="Archived category is not allowed to use"
        ):
            await transaction_service.create_transaction(data, user_id)

        category_repo_mock.get_by_id.assert_called_once()

        transaction_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_transaction_inactive_currency(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_currency: Currency,
        data: TransactionCreate,
    ):
        user_id = 1
        existing_currency.is_active = False

        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await transaction_service.create_transaction(data, user_id)

        currency_repo_mock.get_by_code.assert_called_once()

        transaction_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_transaction_with_splits(
        self,
        mocker: MockerFixture,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionCreate,
    ):
        user_id = existing_category.user_id
        data.category_id = None
        data.splits = [
            TransactionSplitCreate(
                category_id=existing_category.id,
                amount=Decimal("800.00"),
                description="Groceries",
            ),
            TransactionSplitCreate(
                category_id=existing_category.id + 1,
                amount=Decimal("200.00"),
            ),
        ]
        data.amount = Decimal("1000.00")

        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = existing_category
        account_repo_mock.get_by_id.return_value = existing_account

        transaction_repo_mock.add.side_effect = as_persisted
        transaction_split_repo_mock.add_all.side_effect = as_persisted_all

        validate_category_spy = mocker.spy(validators, "validate_category")
        validate_currency_spy = mocker.spy(validators, "validate_currency")
        validate_account_spy = mocker.spy(validators, "validate_account")
        resolve_settled_amount_spy = mocker.spy(validators, "resolve_settled_amount")
        resolve_splits_spy = mocker.spy(validators, "resolve_splits")

        await transaction_service.create_transaction(data, user_id)

        created_transaction = transaction_repo_mock.add.call_args[0][0]

        assert created_transaction.category_id is None

        splits = transaction_split_repo_mock.add_all.call_args[0][0]

        assert len(splits) == 2

        assert_model_fields(
            splits[0],
            transaction_id=created_transaction.id,
            category_id=existing_category.id,
            amount=Decimal("800.00"),
            settled_amount=Decimal("800.00"),
            description="Groceries",
        )

        assert_model_fields(
            splits[1],
            transaction_id=created_transaction.id,
            category_id=existing_category.id + 1,
            amount=Decimal("200.00"),
            settled_amount=Decimal("200.00"),
        )

        assert validate_category_spy.call_count == 3

        assert category_repo_mock.get_by_id.call_count == 2

        validate_currency_spy.assert_called_once_with(
            transaction_service.currency_repository, existing_currency.code
        )

        validate_account_spy.assert_called_once_with(
            transaction_service.account_repository, user_id, existing_account.id
        )

        resolve_settled_amount_spy.assert_called_once_with(
            existing_account,
            data.currency_code,
            data.amount,
            data.settled_amount,
        )

        resolve_splits_spy.assert_called_once_with(
            data.amount,
            data.amount,
            data.splits,
        )

        transaction_split_repo_mock.add_all.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_create_transaction_splits_deduplicate_categories(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        existing_account: Account,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionCreate,
    ):
        """Three parts of one receipt share a category: it is validated once, not three times."""
        user_id = existing_category.user_id
        data.category_id = None
        data.amount = Decimal("1000.00")
        data.splits = [
            TransactionSplitCreate(category_id=existing_category.id, amount=Decimal("300.00")),
            TransactionSplitCreate(category_id=existing_category.id, amount=Decimal("300.00")),
            TransactionSplitCreate(category_id=existing_category.id, amount=Decimal("400.00")),
        ]

        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = existing_category
        account_repo_mock.get_by_id.return_value = existing_account

        transaction_repo_mock.add.side_effect = as_persisted
        transaction_split_repo_mock.add_all.side_effect = as_persisted_all

        await transaction_service.create_transaction(data, user_id)

        category_repo_mock.get_by_id.assert_called_once_with(existing_category.id)

        splits = transaction_split_repo_mock.add_all.call_args[0][0]

        assert len(splits) == 3

    async def test_create_transaction_splits_archived_category(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionCreate,
    ):
        """Splits are validated before anything is written: the transaction is never created."""
        user_id = existing_category.user_id
        data.category_id = None
        data.amount = Decimal("1000.00")
        data.splits = [
            TransactionSplitCreate(category_id=existing_category.id, amount=Decimal("800.00")),
            TransactionSplitCreate(category_id=existing_category.id, amount=Decimal("200.00")),
        ]

        existing_category.archived_at = datetime.now(UTC)

        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = existing_category
        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(
            NotAllowedActionException, match="Archived category is not allowed to use"
        ):
            await transaction_service.create_transaction(data, user_id)

        transaction_repo_mock.add.assert_not_called()

        transaction_split_repo_mock.add_all.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_transaction_splits_fail_nothing_committed(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionCreate,
    ):
        """Transaction and its splits belong to one operation: if splits fail, nothing is kept."""
        user_id = existing_category.user_id
        data.category_id = None
        data.amount = Decimal("1000.00")
        data.splits = [
            TransactionSplitCreate(category_id=existing_category.id, amount=Decimal("800.00")),
            TransactionSplitCreate(category_id=existing_category.id, amount=Decimal("200.00")),
        ]

        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = existing_category
        account_repo_mock.get_by_id.return_value = existing_account

        transaction_repo_mock.add.side_effect = as_persisted
        transaction_split_repo_mock.add_all.side_effect = RuntimeError("db error")

        with pytest.raises(RuntimeError):
            await transaction_service.create_transaction(data, user_id)

        transaction_repo_mock.add.assert_called_once()

        unit_of_work_mock.commit.assert_not_awaited()


class TestGetUserTransactions:
    async def test_get_user_transactions_success(
        self,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        existing_account: Account,
    ):
        user_id = 1

        user_transactions = [
            make_transaction(
                id=1,
                type=TransactionType.EXPENSE,
                kind=TransactionKind.REGULAR,
                amount=Decimal("500.00"),
                currency_code="UAH",
                description="Foods",
                user_id=user_id,
                date=date(2026, 3, 1),
                account_id=existing_account.id,
            ),
            make_transaction(
                id=2,
                type=TransactionType.INCOME,
                kind=TransactionKind.REGULAR,
                amount=Decimal("20000.00"),
                currency_code="UAH",
                description="Salary",
                user_id=user_id,
                date=date(2026, 3, 1),
                account_id=existing_account.id,
            ),
        ]

        transaction_repo_mock.get_by_user.return_value = user_transactions
        transaction_split_repo_mock.get_transaction_ids_with_splits.return_value = set()

        limit = 20
        offset = 0
        filters = TransactionFilters()

        result = await transaction_service.get_user_transactions(
            user_id=user_id, limit=limit, offset=offset, filters=filters
        )

        assert result == [TransactionListItem.model_validate(t) for t in user_transactions]

        transaction_repo_mock.get_by_user.assert_called_once_with(user_id, filters, limit, offset)
        transaction_split_repo_mock.get_transaction_ids_with_splits.assert_called_once()

    async def test_get_user_empty_transactions(
        self,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
    ):
        user_id = 1

        user_transactions = []

        transaction_repo_mock.get_by_user.return_value = user_transactions

        limit = 20
        offset = 0
        filters = TransactionFilters()

        result = await transaction_service.get_user_transactions(
            user_id=user_id, limit=limit, offset=offset, filters=filters
        )

        assert result == [TransactionListItem.model_validate(t) for t in user_transactions]

        transaction_repo_mock.get_by_user.assert_called_once_with(user_id, filters, limit, offset)

    async def test_get_user_transactions_maps_counterpart_only_to_transfers(
        self,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        existing_account: Account,
    ):
        user_id = 1
        group_id = uuid.uuid4()

        regular = make_transaction(
            id=1,
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            amount=Decimal("500.00"),
            currency_code="UAH",
            description="Foods",
            user_id=user_id,
            date=date(2026, 3, 1),
            account_id=existing_account.id,
        )

        transfer_side = make_transaction(
            id=2,
            type=TransactionType.EXPENSE,
            kind=TransactionKind.TRANSFER,
            amount=Decimal("1000.00"),
            currency_code="UAH",
            description="Transfer out",
            user_id=user_id,
            date=date(2026, 3, 1),
            account_id=existing_account.id,
            transfer_group_id=group_id,
        )

        transaction_repo_mock.get_by_user.return_value = [regular, transfer_side]
        transaction_repo_mock.get_counterpart_account_ids.return_value = {transfer_side.id: 777}

        result = await transaction_service.get_user_transactions(
            user_id=user_id, filters=TransactionFilters(), limit=20, offset=0
        )

        assert result[0].counterpart_account_id is None
        assert result[1].counterpart_account_id == 777

        transaction_repo_mock.get_counterpart_account_ids.assert_called_once_with(
            [group_id], user_id
        )

    async def test_get_user_transactions_without_transfers_skips_counterpart_query(
        self,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        existing_account: Account,
    ):
        transaction_repo_mock.get_by_user.return_value = [
            make_transaction(
                id=1,
                type=TransactionType.EXPENSE,
                kind=TransactionKind.REGULAR,
                amount=Decimal("500.00"),
                currency_code="UAH",
                description="Foods",
                user_id=1,
                date=date(2026, 3, 1),
                account_id=existing_account.id,
            )
        ]

        await transaction_service.get_user_transactions(
            user_id=1, filters=TransactionFilters(), limit=20, offset=0
        )

        transaction_repo_mock.get_counterpart_account_ids.assert_not_called()

    async def test_get_user_transactions_marks_transactions_with_splits(
        self,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        existing_account: Account,
    ):
        user_id = 1

        user_transactions = [
            make_transaction(
                id=1,
                type=TransactionType.EXPENSE,
                kind=TransactionKind.REGULAR,
                amount=Decimal("500.00"),
                currency_code="UAH",
                description="Foods",
                user_id=user_id,
                date=date(2026, 3, 1),
                account_id=existing_account.id,
            ),
            make_transaction(
                id=2,
                type=TransactionType.INCOME,
                kind=TransactionKind.REGULAR,
                amount=Decimal("20000.00"),
                currency_code="UAH",
                description="Salary",
                user_id=user_id,
                date=date(2026, 3, 1),
                account_id=existing_account.id,
            ),
        ]

        transaction_repo_mock.get_by_user.return_value = user_transactions
        transaction_split_repo_mock.get_transaction_ids_with_splits.return_value = {2}

        limit = 20
        offset = 0
        filters = TransactionFilters()

        result = await transaction_service.get_user_transactions(
            user_id=user_id, limit=limit, offset=offset, filters=filters
        )

        assert result[0].has_splits is False
        assert result[1].has_splits is True

        transaction_repo_mock.get_by_user.assert_called_once_with(user_id, filters, limit, offset)
        transaction_split_repo_mock.get_transaction_ids_with_splits.assert_called_once_with([1, 2])


class TestUpdateTransaction:
    @pytest.fixture
    def data(
        self,
        existing_transaction: Transaction,
        existing_account: Account,
    ):
        return TransactionUpdate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100.00"),
            currency_code=existing_transaction.currency_code,
            description="Foods",
            date=date(2026, 3, 1),
            account_id=existing_account.id,
        )

    async def test_update_transaction_success(
        self,
        mocker: MockerFixture,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
        existing_account: Account,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionUpdate,
    ):
        data.category_id = existing_category.id
        user_id = existing_transaction.user_id

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_id.return_value = existing_account
        transaction_split_repo_mock.get_by_transaction.return_value = []

        transaction_repo_mock.update.side_effect = as_persisted

        validate_transaction_spy = mocker.spy(validators, "validate_transaction")
        validate_category_spy = mocker.spy(validators, "validate_category")
        validate_currency_spy = mocker.spy(validators, "validate_currency")
        validate_account_spy = mocker.spy(validators, "validate_account")
        resolve_settled_amount_spy = mocker.spy(validators, "resolve_settled_amount")

        result = await transaction_service.update_transaction(
            existing_transaction.id, data, user_id
        )

        call_args = transaction_repo_mock.update.call_args[0][0]

        assert result == TransactionResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            amount=data.amount,
            type=data.type,
            kind=TransactionKind.REGULAR,
            user_id=existing_transaction.user_id,
            category_id=data.category_id,
            currency_code=data.currency_code,
            settled_amount=data.amount,
            settled_currency_code=existing_account.currency_code,
            date=data.date,
            account_id=data.account_id,
        )

        validate_transaction_spy.assert_called_once_with(
            transaction_service.transaction_repository, user_id, existing_transaction.id
        )

        validate_category_spy.assert_called_once_with(
            transaction_service.category_repository,
            user_id,
            existing_category.id,
            allow_archived=False,
        )

        validate_currency_spy.assert_called_once_with(
            transaction_service.currency_repository, data.currency_code, allow_inactive=True
        )

        validate_account_spy.assert_called_once_with(
            transaction_service.account_repository,
            user_id,
            existing_account.id,
            allow_archived=True,
        )

        resolve_settled_amount_spy.assert_called_once_with(
            existing_account,
            data.currency_code,
            data.amount,
            data.settled_amount,
        )

        transaction_repo_mock.get_by_id.assert_called_once()

        transaction_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_transaction_preserves_adjustment_kind(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        existing_account: Account,
        existing_transaction: Transaction,
        existing_currency: Currency,
        data: TransactionUpdate,
    ):
        existing_transaction.kind = TransactionKind.ADJUSTMENT
        data.category_id = None

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_id.return_value = existing_account
        transaction_split_repo_mock.get_by_transaction.return_value = []

        transaction_repo_mock.update.side_effect = as_persisted

        await transaction_service.update_transaction(
            existing_transaction.id,
            data,
            existing_transaction.user_id,
        )

        call_args = transaction_repo_mock.update.call_args[0][0]
        assert call_args.kind == TransactionKind.ADJUSTMENT

    async def test_update_transaction_not_found_transaction(
        self,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        unit_of_work_mock: UnitOfWork,
        data: TransactionUpdate,
    ):
        transaction_id = 999
        user_id = 1

        transaction_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Transaction not found"):
            await transaction_service.update_transaction(transaction_id, data, user_id)

        transaction_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_transaction_without_category(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_transaction: Transaction,
        existing_currency: Currency,
        data: TransactionUpdate,
    ):
        data.category_id = None
        user_id = 1

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = None
        account_repo_mock.get_by_id.return_value = existing_account
        transaction_split_repo_mock.get_by_transaction.return_value = []

        transaction_repo_mock.update.side_effect = as_persisted

        result = await transaction_service.update_transaction(
            existing_transaction.id, data, user_id
        )

        call_args = transaction_repo_mock.update.call_args[0][0]

        assert result == TransactionResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            amount=data.amount,
            type=data.type,
            kind=TransactionKind.REGULAR,
            category_id=data.category_id,
            settled_amount=data.amount,
            settled_currency_code=existing_account.currency_code,
            user_id=user_id,
            date=data.date,
            account_id=data.account_id,
        )

        currency_repo_mock.get_by_code.assert_called_once()

        category_repo_mock.get_by_id.assert_not_called()

        transaction_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_transaction_different_currency_success(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
        existing_account: Account,
        existing_usd_currency: Currency,
        data: TransactionUpdate,
    ):
        """A USD purchase on a UAH card: the account is charged in UAH."""
        data.category_id = None
        data.currency_code = existing_usd_currency.code
        data.amount = Decimal("24.00")
        data.settled_amount = Decimal("1000.00")

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        currency_repo_mock.get_by_code.return_value = existing_usd_currency
        account_repo_mock.get_by_id.return_value = existing_account
        transaction_split_repo_mock.get_by_transaction.return_value = []

        transaction_repo_mock.update.side_effect = as_persisted

        result = await transaction_service.update_transaction(
            existing_transaction.id,
            data,
            existing_transaction.user_id,
        )

        call_args = transaction_repo_mock.update.call_args[0][0]

        assert result == TransactionResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            amount=data.amount,
            currency_code=existing_usd_currency.code,
            settled_amount=data.settled_amount,
            settled_currency_code=existing_account.currency_code,
        )

        transaction_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_transaction_different_currency_without_settled_amount(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
        existing_account: Account,
        existing_usd_currency: Currency,
        data: TransactionUpdate,
    ):
        data.category_id = None
        data.currency_code = existing_usd_currency.code
        data.amount = Decimal("24.00")

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        currency_repo_mock.get_by_code.return_value = existing_usd_currency
        account_repo_mock.get_by_id.return_value = existing_account
        transaction_split_repo_mock.get_by_transaction.return_value = []

        with pytest.raises(
            NotAllowedActionException,
            match="Amount charged to the account is required, in the account currency",
        ):
            await transaction_service.update_transaction(
                existing_transaction.id,
                data,
                existing_transaction.user_id,
            )

        transaction_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_transaction_archived_category(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        category_repo_mock: CategoryRepository,
        existing_account: Account,
        existing_transaction: Transaction,
        existing_category: Category,
        data: TransactionUpdate,
    ):
        data.category_id = existing_category.id
        existing_category.archived_at = datetime.now(UTC)

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        category_repo_mock.get_by_id.return_value = existing_category
        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(
            NotAllowedActionException, match="Archived category is not allowed to use"
        ):
            await transaction_service.update_transaction(
                existing_transaction.id, data, existing_transaction.user_id
            )

        transaction_repo_mock.update.assert_not_called()

    async def test_update_transaction_inactive_currency(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        currency_repo_mock: CurrencyRepository,
        existing_account: Account,
        existing_transaction: Transaction,
        existing_currency: Currency,
        data: TransactionUpdate,
    ):
        """Switching to an inactive currency → NotAllowedActionException"""

        data.currency_code = "USD"
        existing_currency.code = "USD"
        existing_currency.is_active = False

        currency_repo_mock.get_by_code.return_value = existing_currency
        transaction_repo_mock.get_by_id.return_value = existing_transaction
        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await transaction_service.update_transaction(
                existing_transaction.id, data, existing_transaction.user_id
            )

        transaction_repo_mock.update.assert_not_called()

    async def test_update_transaction_keeps_inactive_currency_allowed(
        self,
        mocker: MockerFixture,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        category_repo_mock: CategoryRepository,
        currency_repo_mock: CurrencyRepository,
        account_repo_mock: AccountRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
        existing_category: Category,
        existing_currency: Currency,
        existing_account: Account,
        data: TransactionUpdate,
    ):
        existing_currency.is_active = False

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_id.return_value = existing_account
        transaction_repo_mock.update.return_value = existing_transaction
        transaction_split_repo_mock.get_by_transaction.return_value = []

        validate_currency_spy = mocker.spy(validators, "validate_currency")

        await transaction_service.update_transaction(
            existing_transaction.id,
            data,
            existing_transaction.user_id,
        )

        validate_currency_spy.assert_called_once_with(
            transaction_service.currency_repository,
            data.currency_code,
            allow_inactive=True,
        )

        transaction_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_transaction_keeps_archived_category_allowed(
        self,
        mocker: MockerFixture,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        category_repo_mock: CategoryRepository,
        currency_repo_mock: CurrencyRepository,
        account_repo_mock: AccountRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
        existing_category: Category,
        existing_currency: Currency,
        existing_account: Account,
        data: TransactionUpdate,
    ):
        existing_category.archived_at = datetime.now(UTC)

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_id.return_value = existing_account
        transaction_repo_mock.update.return_value = existing_transaction
        transaction_split_repo_mock.get_by_transaction.return_value = []

        validate_category_spy = mocker.spy(validators, "validate_category")

        await transaction_service.update_transaction(
            existing_transaction.id,
            data,
            existing_transaction.user_id,
        )

        validate_category_spy.assert_called_once_with(
            transaction_service.category_repository,
            existing_transaction.user_id,
            data.category_id,
            allow_archived=True,
        )

        transaction_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_transaction_transfer_rejected(
        self,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
        data: TransactionUpdate,
    ):
        existing_transaction.kind = TransactionKind.TRANSFER
        existing_transaction.transfer_group_id = uuid.uuid4()

        transaction_repo_mock.get_by_id.return_value = existing_transaction

        with pytest.raises(
            NotAllowedActionException, match="Transfer cannot be edited one side at a time"
        ):
            await transaction_service.update_transaction(
                existing_transaction.id,
                data,
                existing_transaction.user_id,
            )

        transaction_repo_mock.update.assert_not_called()

        category_repo_mock.get_by_id.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_transaction_replaces_splits(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
        existing_account: Account,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionUpdate,
    ):
        user_id = existing_transaction.user_id
        data.category_id = None
        data.amount = Decimal("1000.00")
        data.splits = [
            TransactionSplitCreate(category_id=existing_category.id, amount=Decimal("700.00")),
            TransactionSplitCreate(category_id=existing_category.id + 1, amount=Decimal("300.00")),
        ]

        old_splits = [
            TransactionSplit(
                id=1,
                transaction_id=existing_transaction.id,
                category_id=existing_category.id,
                amount=Decimal("800.00"),
                settled_amount=Decimal("800.00"),
            ),
            TransactionSplit(
                id=2,
                transaction_id=existing_transaction.id,
                category_id=existing_category.id + 1,
                amount=Decimal("200.00"),
                settled_amount=Decimal("200.00"),
            ),
        ]

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        transaction_split_repo_mock.get_by_transaction.return_value = old_splits
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_id.return_value = existing_account

        transaction_repo_mock.update.side_effect = as_persisted
        transaction_split_repo_mock.add_all.side_effect = as_persisted_all

        result = await transaction_service.update_transaction(
            existing_transaction.id, data, user_id
        )

        transaction_split_repo_mock.delete_by_transaction.assert_called_once_with(
            existing_transaction.id
        )

        new_splits = transaction_split_repo_mock.add_all.call_args[0][0]

        assert len(new_splits) == 2

        assert_model_fields(
            new_splits[0],
            transaction_id=existing_transaction.id,
            category_id=existing_category.id,
            amount=Decimal("700.00"),
            settled_amount=Decimal("700.00"),
        )

        assert_model_fields(
            new_splits[1],
            transaction_id=existing_transaction.id,
            category_id=existing_category.id + 1,
            amount=Decimal("300.00"),
            settled_amount=Decimal("300.00"),
        )

        assert result.has_splits is True

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_transaction_removes_splits(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
        existing_account: Account,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionUpdate,
    ):
        user_id = existing_transaction.user_id
        data.category_id = existing_category.id
        data.splits = None

        old_splits = [
            TransactionSplit(
                id=1,
                transaction_id=existing_transaction.id,
                category_id=existing_category.id,
                amount=Decimal("800.00"),
                settled_amount=Decimal("800.00"),
            ),
            TransactionSplit(
                id=2,
                transaction_id=existing_transaction.id,
                category_id=existing_category.id + 1,
                amount=Decimal("200.00"),
                settled_amount=Decimal("200.00"),
            ),
        ]

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        transaction_split_repo_mock.get_by_transaction.return_value = old_splits
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_id.return_value = existing_account

        transaction_repo_mock.update.side_effect = as_persisted

        result = await transaction_service.update_transaction(
            existing_transaction.id, data, user_id
        )

        transaction_split_repo_mock.delete_by_transaction.assert_called_once_with(
            existing_transaction.id
        )

        transaction_split_repo_mock.add_all.assert_not_called()

        assert result.has_splits is False
        assert result.splits is None

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_transaction_adds_splits(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
        existing_account: Account,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionUpdate,
    ):
        user_id = existing_transaction.user_id
        data.category_id = None
        data.amount = Decimal("1000.00")
        data.splits = [
            TransactionSplitCreate(category_id=existing_category.id, amount=Decimal("600.00")),
            TransactionSplitCreate(category_id=existing_category.id + 1, amount=Decimal("400.00")),
        ]

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        transaction_split_repo_mock.get_by_transaction.return_value = []
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_id.return_value = existing_account

        transaction_repo_mock.update.side_effect = as_persisted
        transaction_split_repo_mock.add_all.side_effect = as_persisted_all

        await transaction_service.update_transaction(existing_transaction.id, data, user_id)

        transaction_split_repo_mock.delete_by_transaction.assert_not_called()

        new_splits = transaction_split_repo_mock.add_all.call_args[0][0]

        assert len(new_splits) == 2

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_transaction_keeps_archived_split_category_allowed(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
        existing_account: Account,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionUpdate,
    ):
        user_id = existing_transaction.user_id
        data.category_id = None
        data.amount = Decimal("1000.00")
        data.splits = [
            TransactionSplitCreate(category_id=existing_category.id, amount=Decimal("600.00")),
            TransactionSplitCreate(category_id=existing_category.id, amount=Decimal("400.00")),
        ]

        existing_category.archived_at = datetime.now(UTC)

        old_splits = [
            TransactionSplit(
                id=1,
                transaction_id=existing_transaction.id,
                category_id=existing_category.id,
                amount=Decimal("1000.00"),
                settled_amount=Decimal("1000.00"),
            ),
        ]

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        transaction_split_repo_mock.get_by_transaction.return_value = old_splits
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_id.return_value = existing_account

        transaction_repo_mock.update.side_effect = as_persisted
        transaction_split_repo_mock.add_all.side_effect = as_persisted_all

        await transaction_service.update_transaction(existing_transaction.id, data, user_id)

        transaction_split_repo_mock.add_all.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_transaction_new_archived_split_category_rejected(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_split_repo_mock: TransactionSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_transaction: Transaction,
        existing_account: Account,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionUpdate,
    ):
        user_id = existing_transaction.user_id
        data.category_id = None
        data.amount = Decimal("1000.00")
        data.splits = [
            TransactionSplitCreate(category_id=existing_category.id, amount=Decimal("600.00")),
            TransactionSplitCreate(category_id=existing_category.id, amount=Decimal("400.00")),
        ]

        existing_category.archived_at = datetime.now(UTC)

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        transaction_split_repo_mock.get_by_transaction.return_value = []
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(
            NotAllowedActionException, match="Archived category is not allowed to use"
        ):
            await transaction_service.update_transaction(existing_transaction.id, data, user_id)

        transaction_repo_mock.update.assert_not_called()

        transaction_split_repo_mock.add_all.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()
