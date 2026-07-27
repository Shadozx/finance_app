from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pytest_mock import MockerFixture

from app.services import TransactionService, validators
from app.repositories import TransactionRepository, CurrencyRepository, CategoryRepository, \
    TransactionTemplateRepository
from app.models import Transaction, TransactionType, TransactionKind, Currency, Category, TransactionTemplate
from app.schemas import TransactionResponse, TransactionCreate, TransactionUpdate, TransactionFilters, \
    UseTemplateRequest
from app.core.exceptions import NotFoundException, NotAllowedActionException
from tests.units.services.helpers import assert_model_fields


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

        result = await transaction_service.get_transaction(
            transaction_id,
            user_id
        )

        assert result == TransactionResponse.model_validate(existing_transaction)

        validate_transaction_spy.assert_called_once_with(
            transaction_service.transaction_repository,
            user_id,
            transaction_id
        )

        transaction_repo_mock.get_by_id.assert_called_once()

    async def test_get_transaction_not_found_transaction(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository
    ):
        user_id = 1
        transaction_id = 999

        transaction_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Transaction not found"):
            await transaction_service.get_transaction(
                transaction_id,
                user_id
            )

        transaction_repo_mock.get_by_id.assert_called_once()


class TestDeleteTransaction:
    async def test_delete_transaction_success(
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

        await transaction_service.delete_transaction(
            transaction_id,
            user_id
        )

        validate_transaction_spy.assert_called_once_with(
            transaction_service.transaction_repository,
            user_id,
            transaction_id
        )

        transaction_repo_mock.get_by_id.assert_called_once()

        transaction_repo_mock.delete.assert_called_once()

    async def test_delete_transaction_not_found(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository
    ):
        user_id = 1
        transaction_id = 999

        transaction_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Transaction not found"):
            await transaction_service.delete_transaction(
                transaction_id,
                user_id
            )

        transaction_repo_mock.get_by_id.assert_called_once()

        transaction_repo_mock.delete.assert_not_called()


class TestCreateTransaction:

    @pytest.fixture
    def data(
            self,
            existing_transaction: Transaction,
            existing_currency: Currency,
    ):
        return TransactionCreate(
            type=existing_transaction.type,
            amount=existing_transaction.amount,
            currency_code=existing_transaction.currency_code,
            description=existing_transaction.description,
            date=existing_transaction.date,
        )

    async def test_create_transaction_success(
            self,
            mocker: MockerFixture,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
            category_repo_mock: CategoryRepository,
            existing_currency: Currency,
            existing_category: Category,
            data: TransactionCreate
    ):
        user_id = existing_category.user_id
        data.category_id = existing_category.id

        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = existing_category

        created = Transaction(
            id=1,
            type=data.type,
            kind=TransactionKind.REGULAR,
            amount=data.amount,
            currency_code=data.currency_code,
            category_id=data.category_id,
            description=data.description,
            date=data.date,
            user_id=user_id,
        )

        transaction_repo_mock.create.return_value = created

        validate_category_spy = mocker.spy(validators, "validate_category")
        validate_currency_spy = mocker.spy(validators, "validate_currency")

        result = await transaction_service.create_transaction(
            data,
            user_id
        )

        assert result == TransactionResponse.model_validate(created)

        call_args = transaction_repo_mock.create.call_args[0][0]
        assert_model_fields(
            call_args,
            amount=data.amount,
            type=data.type,
            kind=TransactionKind.REGULAR,
            user_id=user_id,
            category_id=data.category_id,
            currency_code=data.currency_code,
            date=data.date
        )

        validate_category_spy.assert_called_once_with(
            transaction_service.category_repository,
            user_id,
            existing_category.id
        )
        validate_currency_spy.assert_called_once_with(
            transaction_service.currency_repository,
            existing_currency.code
        )

        transaction_repo_mock.create.assert_called_once()

    async def test_create_transaction_without_category(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
            category_repo_mock: CategoryRepository,
            existing_currency: Currency,
            data: TransactionCreate
    ):
        data.category_id = None
        user_id = 1

        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = None

        created = Transaction(
            id=1,
            type=data.type,
            kind=TransactionKind.REGULAR,
            amount=data.amount,
            currency_code=data.currency_code,
            description=data.description,
            date=data.date,
            user_id=user_id,
        )

        transaction_repo_mock.create.return_value = created

        result = await transaction_service.create_transaction(
            data,
            user_id
        )

        assert result == TransactionResponse.model_validate(created)

        call_args = transaction_repo_mock.create.call_args[0][0]
        assert_model_fields(
            call_args,
            amount=data.amount,
            type=data.type,
            kind=TransactionKind.REGULAR,
            category_id=data.category_id,
            user_id=user_id,
            date=data.date
        )

        currency_repo_mock.get_by_code.assert_called_once()

        category_repo_mock.get_by_id.assert_not_called()

        transaction_repo_mock.create.assert_called_once()

    async def test_create_transaction_archived_category(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            category_repo_mock: CategoryRepository,
            existing_category: Category,
            data: TransactionCreate
    ):
        data.category_id = existing_category.id
        user_id = 1
        existing_category.archived_at = datetime.now(timezone.utc)

        category_repo_mock.get_by_id.return_value = existing_category

        with pytest.raises(NotAllowedActionException, match="Archived category is not allowed to use"):
            await transaction_service.create_transaction(
                data,
                user_id
            )

        category_repo_mock.get_by_id.assert_called_once()

        transaction_repo_mock.create.assert_not_called()

    async def test_create_transaction_inactive_currency(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
            existing_currency: Currency,
            data: TransactionCreate
    ):
        user_id = 1
        existing_currency.is_active = False

        currency_repo_mock.get_by_code.return_value = existing_currency

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await transaction_service.create_transaction(
                data,
                user_id
            )

        currency_repo_mock.get_by_code.assert_called_once()

        transaction_repo_mock.create.assert_not_called()


class TestCreateTransactionFromTemplate:
    @pytest.fixture
    def data(
            self,

    ):
        return UseTemplateRequest(
            amount=Decimal("500.00"),
            description="Early Morning Coffee expense",
            date=date(2026, 3, 1)
        )

    async def test_create_transaction_from_template_success(
            self,
            mocker: MockerFixture,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            transaction_template_repo_mock: TransactionTemplateRepository,
            category_repo_mock: CategoryRepository,
            existing_template: TransactionTemplate,
            existing_category: Category,
            data: UseTemplateRequest,
    ):
        data.category_id = existing_category.id
        user_id = existing_template.user_id
        template_id = existing_template.id

        transaction_template_repo_mock.get_by_id.return_value = existing_template
        category_repo_mock.get_by_id.return_value = existing_category

        created = Transaction(
            id=1,
            type=existing_template.type,
            kind=TransactionKind.REGULAR,
            amount=data.amount,
            currency_code=existing_template.currency_code,
            category_id=data.category_id,
            description=data.description,
            date=data.date,
            user_id=user_id,
        )

        transaction_repo_mock.create.return_value = created

        validate_template_spy = mocker.spy(validators, "validate_template")
        validate_category_spy = mocker.spy(validators, "validate_category")
        validate_currency_spy = mocker.spy(validators, "validate_currency")

        result = await transaction_service.create_transaction_from_template(
            template_id,
            data,
            user_id
        )

        assert result == TransactionResponse.model_validate(created)

        call_args = transaction_repo_mock.create.call_args[0][0]
        assert_model_fields(
            call_args,
            type=existing_template.type,
            kind=TransactionKind.REGULAR,
            amount=data.amount,
            currency_code=existing_template.currency_code,
            category_id=data.category_id,
            description=data.description,
            date=data.date,
            user_id=user_id,
        )

        validate_template_spy.assert_called_once_with(
            transaction_service.transaction_template_repository,
            user_id,
            template_id
        )

        validate_category_spy.assert_called_once_with(
            transaction_service.category_repository,
            user_id,
            data.category_id
        )

        validate_currency_spy.assert_called_once_with(
            transaction_service.currency_repository,
            existing_template.currency_code
        )

        transaction_repo_mock.create.assert_called_once()

    async def test_create_transaction_from_template_without_category(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            transaction_template_repo_mock: TransactionTemplateRepository,
            existing_template: TransactionTemplate,
            data: UseTemplateRequest,
    ):
        data.category_id = None
        user_id = existing_template.user_id
        template_id = existing_template.id

        transaction_template_repo_mock.get_by_id.return_value = existing_template

        created = Transaction(
            id=1,
            type=existing_template.type,
            kind=TransactionKind.REGULAR,
            amount=data.amount,
            currency_code=existing_template.currency_code,
            description=data.description,
            date=data.date,
            user_id=user_id,
        )

        transaction_repo_mock.create.return_value = created

        result = await transaction_service.create_transaction_from_template(
            template_id,
            data,
            user_id
        )

        assert result == TransactionResponse.model_validate(created)

        call_args = transaction_repo_mock.create.call_args[0][0]
        assert_model_fields(
            call_args,
            type=existing_template.type,
            kind=TransactionKind.REGULAR,
            amount=data.amount,
            currency_code=existing_template.currency_code,
            category_id=data.category_id,
            description=data.description,
            date=data.date,
            user_id=user_id,
        )

        transaction_repo_mock.create.assert_called_once()

    async def test_create_transaction_from_template_not_found_template(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            transaction_template_repo_mock: TransactionTemplateRepository,
            data: UseTemplateRequest,
    ):
        user_id = 1
        template_id = 999

        transaction_template_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Transaction template not found"):
            await transaction_service.create_transaction_from_template(
                template_id,
                data,
                user_id
            )

        transaction_repo_mock.create.assert_not_called()

    async def test_create_transaction_archived_category(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            transaction_template_repo_mock: TransactionTemplateRepository,
            category_repo_mock: CategoryRepository,
            existing_template: TransactionTemplate,
            existing_category: Category,
            data: UseTemplateRequest
    ):
        data.category_id = existing_category.id
        user_id = existing_template.user_id
        existing_category.archived_at = datetime.now(timezone.utc)

        transaction_template_repo_mock.get_by_id.return_value = existing_template
        category_repo_mock.get_by_id.return_value = existing_category

        with pytest.raises(NotAllowedActionException, match="Archived category is not allowed to use"):
            await transaction_service.create_transaction_from_template(
                existing_template.id,
                data,
                user_id
            )

        transaction_repo_mock.create.assert_not_called()

    async def test_create_transaction_inactive_currency(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            transaction_template_repo_mock: TransactionTemplateRepository,
            currency_repo_mock: CurrencyRepository,
            existing_template: TransactionTemplate,
            existing_currency: Currency,
            data: UseTemplateRequest
    ):
        user_id = existing_template.user_id
        existing_currency.is_active = False

        transaction_template_repo_mock.get_by_id.return_value = existing_template
        currency_repo_mock.get_by_code.return_value = existing_currency

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await transaction_service.create_transaction_from_template(
                existing_template.id,
                data,
                user_id
            )

        transaction_repo_mock.create.assert_not_called()


class TestGetUserTransactions:

    async def test_get_user_transactions_success(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
    ):
        user_id = 1

        user_transactions = [
            Transaction(
                id=1,
                type=TransactionType.EXPENSE,
                kind=TransactionKind.REGULAR,
                amount=Decimal("500.00"),
                currency_code="UAH",
                description="Foods",
                user_id=user_id,
                date=date(2026, 3, 1),
            ),
            Transaction(
                id=2,
                type=TransactionType.INCOME,
                kind=TransactionKind.REGULAR,
                amount=Decimal("20000.00"),
                currency_code="UAH",
                description="Salary",
                user_id=user_id,
                date=date(2026, 3, 1),
            )
        ]

        transaction_repo_mock.get_by_user.return_value = user_transactions

        limit = 20
        offset = 0
        filters = TransactionFilters()

        result = await transaction_service.get_user_transactions(user_id=user_id, limit=limit, offset=offset,
                                                                 filters=filters)

        assert result == [
            TransactionResponse.model_validate(t) for t in user_transactions
        ]

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

        result = await transaction_service.get_user_transactions(user_id=user_id, limit=limit, offset=offset,
                                                                 filters=filters)

        assert result == [
            TransactionResponse.model_validate(t) for t in user_transactions
        ]

        transaction_repo_mock.get_by_user.assert_called_once_with(user_id, filters, limit, offset)


class TestUpdateTransaction:

    @pytest.fixture
    def data(
            self,
            existing_transaction: Transaction,
    ):
        return TransactionUpdate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100.00"),
            currency_code=existing_transaction.currency_code,
            description="Foods",
            date=date(2026, 3, 1),
        )

    async def test_update_transaction_success(
            self,
            mocker: MockerFixture,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
            category_repo_mock: CategoryRepository,
            existing_transaction: Transaction,
            existing_currency: Currency,
            existing_category: Category,
            data: TransactionUpdate
    ):
        data.category_id = existing_category.id
        user_id = existing_transaction.user_id

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency

        updated = Transaction(
            id=existing_transaction.id,
            type=data.type,
            kind=TransactionKind.REGULAR,
            amount=data.amount,
            currency_code=data.currency_code,
            category_id=data.category_id,
            description=data.description,
            date=data.date,
            user_id=existing_transaction.user_id,
        )
        transaction_repo_mock.update.return_value = updated

        validate_transaction_spy = mocker.spy(validators, "validate_transaction")
        validate_category_spy = mocker.spy(validators, "validate_category")
        validate_currency_spy = mocker.spy(validators, "validate_currency")

        result = await transaction_service.update_transaction(
            existing_transaction.id,
            data,
            user_id
        )

        assert result == TransactionResponse.model_validate(updated)

        call_args = transaction_repo_mock.update.call_args[0][0]
        assert_model_fields(
            call_args,
            amount=data.amount,
            type=data.type,
            kind=TransactionKind.REGULAR,
            user_id=existing_transaction.user_id,
            category_id=data.category_id,
            currency_code=data.currency_code,
            date=data.date
        )

        validate_transaction_spy.assert_called_once_with(
            transaction_service.transaction_repository,
            user_id,
            existing_transaction.id
        )

        validate_category_spy.assert_called_once_with(
            transaction_service.category_repository,
            user_id,
            existing_category.id
        )
        validate_currency_spy.assert_called_once_with(
            transaction_service.currency_repository,
            data.currency_code
        )

        transaction_repo_mock.get_by_id.assert_called_once()

        transaction_repo_mock.update.assert_called_once()

    async def test_update_transaction_preserves_adjustment_kind(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
            existing_transaction: Transaction,
            existing_currency: Currency,
            data: TransactionUpdate,
    ):
        existing_transaction.kind = TransactionKind.ADJUSTMENT
        data.category_id = None

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        currency_repo_mock.get_by_code.return_value = existing_currency
        transaction_repo_mock.update.return_value = existing_transaction

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
            data: TransactionUpdate
    ):
        transaction_id = 999
        user_id = 1

        transaction_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Transaction not found"):
            await transaction_service.update_transaction(
                transaction_id,
                data,
                user_id
            )

        transaction_repo_mock.update.assert_not_called()

    async def test_update_transaction_without_category(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
            category_repo_mock: CategoryRepository,
            existing_transaction: Transaction,
            existing_currency: Currency,
            data: TransactionUpdate
    ):
        data.category_id = None
        user_id = 1

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = None

        created = Transaction(
            id=1,
            type=data.type,
            kind=TransactionKind.REGULAR,
            amount=data.amount,
            currency_code=data.currency_code,
            description=data.description,
            date=data.date,
            user_id=user_id,
        )

        transaction_repo_mock.update.return_value = created

        result = await transaction_service.update_transaction(
            existing_transaction.id,
            data,
            user_id
        )

        assert result == TransactionResponse.model_validate(created)

        call_args = transaction_repo_mock.update.call_args[0][0]
        assert_model_fields(
            call_args,
            amount=data.amount,
            type=data.type,
            kind=TransactionKind.REGULAR,
            category_id=data.category_id,
            user_id=user_id,
            date=data.date
        )

        currency_repo_mock.get_by_code.assert_called_once()

        category_repo_mock.get_by_id.assert_not_called()

        transaction_repo_mock.update.assert_called_once()

    async def test_update_transaction_archived_category(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            category_repo_mock: CategoryRepository,
            existing_transaction: Transaction,
            existing_category: Category,
            data: TransactionUpdate
    ):
        data.category_id = existing_category.id
        existing_category.archived_at = datetime.now(timezone.utc)

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        category_repo_mock.get_by_id.return_value = existing_category

        with pytest.raises(NotAllowedActionException, match="Archived category is not allowed to use"):
            await transaction_service.update_transaction(
                existing_transaction.id,
                data,
                existing_transaction.user_id
            )

        transaction_repo_mock.update.assert_not_called()

    async def test_update_transaction_inactive_currency(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
            existing_transaction: Transaction,
            existing_currency: Currency,
            data: TransactionUpdate
    ):
        existing_currency.is_active = False

        currency_repo_mock.get_by_code.return_value = existing_currency
        transaction_repo_mock.get_by_id.return_value = existing_transaction

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await transaction_service.update_transaction(
                existing_transaction.id,
                data,
                existing_transaction.user_id
            )

        transaction_repo_mock.update.assert_not_called()
