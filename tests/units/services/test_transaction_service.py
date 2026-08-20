import uuid
from datetime import date, datetime, timezone
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
    TransactionTemplate,
    TransactionType,
)
from app.repositories import (
    AccountRepository,
    CategoryRepository,
    CurrencyRepository,
    TransactionRepository,
    TransactionTemplateRepository,
)
from app.schemas import (
    TransactionCreate,
    TransactionFilters,
    TransactionResponse,
    TransactionUpdate,
    UseTemplateRequest,
)
from app.services import TransactionService, validators
from tests.units.services.helpers import as_persisted, assert_model_fields, make_transaction


class TestGetTransaction:
    async def test_get_transaction_success(
        self,
        mocker: MockerFixture,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        existing_transaction: Transaction,
    ):
        user_id = existing_transaction.user_id
        transaction_id = existing_transaction.id

        transaction_repo_mock.get_by_id.return_value = existing_transaction

        validate_transaction_spy = mocker.spy(validators, "validate_transaction")

        result = await transaction_service.get_transaction(transaction_id, user_id)

        assert result == TransactionResponse.model_validate(existing_transaction)

        validate_transaction_spy.assert_called_once_with(
            transaction_service.transaction_repository, user_id, transaction_id
        )

        transaction_repo_mock.get_by_id.assert_called_once()

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
        existing_transaction: Transaction,
    ):
        group_id = uuid.uuid4()
        existing_transaction.kind = TransactionKind.TRANSFER
        existing_transaction.transfer_group_id = group_id

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        transaction_repo_mock.get_counterpart_account_ids.return_value = {
            existing_transaction.id: 777
        }

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
        existing_category.archived_at = datetime.now(timezone.utc)

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


class TestCreateTransactionFromTemplate:
    @pytest.fixture
    def data(self, existing_account: Account):
        return UseTemplateRequest(
            amount=Decimal("500.00"),
            description="Early Morning Coffee expense",
            date=date(2026, 3, 1),
            account_id=existing_account.id,
        )

    async def test_create_transaction_from_template_success(
        self,
        mocker: MockerFixture,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_template_repo_mock: TransactionTemplateRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_template: TransactionTemplate,
        existing_category: Category,
        data: UseTemplateRequest,
    ):
        data.category_id = existing_category.id
        user_id = existing_template.user_id
        template_id = existing_template.id

        transaction_template_repo_mock.get_by_id.return_value = existing_template
        category_repo_mock.get_by_id.return_value = existing_category
        account_repo_mock.get_by_id.return_value = existing_account

        transaction_repo_mock.add.side_effect = as_persisted

        validate_template_spy = mocker.spy(validators, "validate_template")
        validate_category_spy = mocker.spy(validators, "validate_category")
        validate_currency_spy = mocker.spy(validators, "validate_currency")
        validate_account_spy = mocker.spy(validators, "validate_account")
        resolve_settled_amount_spy = mocker.spy(validators, "resolve_settled_amount")

        result = await transaction_service.create_transaction_from_template(
            template_id, data, user_id
        )

        call_args = transaction_repo_mock.add.call_args[0][0]

        assert result == TransactionResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            type=existing_template.type,
            kind=TransactionKind.REGULAR,
            amount=data.amount,
            currency_code=existing_template.currency_code,
            settled_amount=data.amount,
            settled_currency_code=existing_account.currency_code,
            category_id=data.category_id,
            description=data.description,
            date=data.date,
            user_id=user_id,
            account_id=data.account_id,
        )

        validate_template_spy.assert_called_once_with(
            transaction_service.transaction_template_repository, user_id, template_id
        )

        validate_category_spy.assert_called_once_with(
            transaction_service.category_repository, user_id, data.category_id
        )

        validate_currency_spy.assert_called_once_with(
            transaction_service.currency_repository, existing_template.currency_code
        )

        validate_account_spy.assert_called_once_with(
            transaction_service.account_repository, user_id, existing_account.id
        )

        resolve_settled_amount_spy.assert_called_once_with(
            existing_account,
            existing_template.currency_code,
            data.amount,
            data.settled_amount,
        )

        transaction_repo_mock.add.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_create_transaction_from_template_without_category(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_template_repo_mock: TransactionTemplateRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_template: TransactionTemplate,
        data: UseTemplateRequest,
    ):
        data.category_id = None
        user_id = existing_template.user_id
        template_id = existing_template.id

        transaction_template_repo_mock.get_by_id.return_value = existing_template
        account_repo_mock.get_by_id.return_value = existing_account

        transaction_repo_mock.add.side_effect = as_persisted

        result = await transaction_service.create_transaction_from_template(
            template_id, data, user_id
        )

        call_args = transaction_repo_mock.add.call_args[0][0]

        assert result == TransactionResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            type=existing_template.type,
            kind=TransactionKind.REGULAR,
            amount=data.amount,
            currency_code=existing_template.currency_code,
            settled_amount=data.amount,
            settled_currency_code=existing_account.currency_code,
            category_id=data.category_id,
            description=data.description,
            date=data.date,
            user_id=user_id,
            account_id=data.account_id,
        )

        transaction_repo_mock.add.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_create_transaction_from_template_not_found_template(
        self,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
        transaction_template_repo_mock: TransactionTemplateRepository,
        unit_of_work_mock: UnitOfWork,
        data: UseTemplateRequest,
    ):
        user_id = 1
        template_id = 999

        transaction_template_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Transaction template not found"):
            await transaction_service.create_transaction_from_template(template_id, data, user_id)

        transaction_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_transaction_archived_category(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_template_repo_mock: TransactionTemplateRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_template: TransactionTemplate,
        existing_category: Category,
        data: UseTemplateRequest,
    ):
        data.category_id = existing_category.id
        user_id = existing_template.user_id
        existing_category.archived_at = datetime.now(timezone.utc)

        transaction_template_repo_mock.get_by_id.return_value = existing_template
        category_repo_mock.get_by_id.return_value = existing_category
        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(
            NotAllowedActionException, match="Archived category is not allowed to use"
        ):
            await transaction_service.create_transaction_from_template(
                existing_template.id, data, user_id
            )

        transaction_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_transaction_inactive_currency(
        self,
        transaction_service: TransactionService,
        account_repo_mock: AccountRepository,
        transaction_repo_mock: TransactionRepository,
        transaction_template_repo_mock: TransactionTemplateRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_account: Account,
        existing_template: TransactionTemplate,
        existing_currency: Currency,
        data: UseTemplateRequest,
    ):
        user_id = existing_template.user_id
        existing_currency.is_active = False

        transaction_template_repo_mock.get_by_id.return_value = existing_template
        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await transaction_service.create_transaction_from_template(
                existing_template.id, data, user_id
            )

        transaction_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()


class TestGetUserTransactions:
    async def test_get_user_transactions_success(
        self,
        transaction_service: TransactionService,
        transaction_repo_mock: TransactionRepository,
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

        limit = 20
        offset = 0
        filters = TransactionFilters()

        result = await transaction_service.get_user_transactions(
            user_id=user_id, limit=limit, offset=offset, filters=filters
        )

        assert result == [TransactionResponse.model_validate(t) for t in user_transactions]

        transaction_repo_mock.get_by_user.assert_called_once_with(user_id, filters, limit, offset)

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

        assert result == [TransactionResponse.model_validate(t) for t in user_transactions]

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
        existing_category.archived_at = datetime.now(timezone.utc)

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
        existing_category.archived_at = datetime.now(timezone.utc)

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_id.return_value = existing_account
        transaction_repo_mock.update.return_value = existing_transaction

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
