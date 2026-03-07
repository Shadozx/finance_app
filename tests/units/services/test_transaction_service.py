import datetime
from decimal import Decimal

import pytest

from app.services import TransactionService
from app.repositories import TransactionRepository, CurrencyRepository, CategoryRepository
from app.models import Transaction, TransactionType, Currency, Category
from app.schemas import TransactionResponse, TransactionCreate, TransactionUpdate, TransactionFilters
from app.core.exceptions import NotFoundException, PermissionException, NotAllowedActionException


class TestGetTransaction:

    async def test_get_transaction_success(
            self,
            existing_transaction: Transaction,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository
    ):
        transaction_repo_mock.get_by_id.return_value = existing_transaction

        expected = TransactionResponse(
            id=existing_transaction.id,
            type=existing_transaction.type,
            amount=existing_transaction.amount,
            currency_code=existing_transaction.currency_code,
            description=existing_transaction.description,
            date=existing_transaction.date,
            user_id=existing_transaction.user_id
        )

        actual = await transaction_service.get_transaction(existing_transaction.id, existing_transaction.user_id)

        assert actual == expected

        transaction_repo_mock.get_by_id.assert_called_once_with(existing_transaction.id)

    async def test_get_transaction_not_found(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository
    ):
        transaction_repo_mock.get_by_id.return_value = None

        id = 9999

        with pytest.raises(NotFoundException, match="Transaction not found"):
            await transaction_service.get_transaction(id, id)

        transaction_repo_mock.get_by_id.assert_called_once_with(id)

    async def test_get_transaction_wrong_owner(
            self,
            existing_transaction: Transaction,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository
    ):
        transaction_repo_mock.get_by_id.return_value = existing_transaction

        other_user = 20

        with pytest.raises(PermissionException, match="You don't have permission to this transaction"):
            await transaction_service.get_transaction(existing_transaction.id, other_user)

        transaction_repo_mock.get_by_id.assert_called_once_with(existing_transaction.id)


class TestDeleteTransaction:
    async def test_delete_transaction_success(
            self,
            existing_transaction: Transaction,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository
    ):
        transaction_repo_mock.get_by_id.return_value = existing_transaction

        await transaction_service.delete_transaction(existing_transaction.id, existing_transaction.user_id)

        transaction_repo_mock.get_by_id.assert_called_once_with(existing_transaction.id)

    async def test_delete_transaction_not_found(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository
    ):
        transaction_repo_mock.get_by_id.return_value = None

        id = 9999

        with pytest.raises(NotFoundException, match="Transaction not found"):
            await transaction_service.delete_transaction(id, id)

        transaction_repo_mock.get_by_id.assert_called_once_with(id)

    async def test_delete_transaction_wrong_owner(
            self,
            existing_transaction: Transaction,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository
    ):
        transaction_repo_mock.get_by_id.return_value = existing_transaction

        other_user = 20

        with pytest.raises(PermissionException, match="You don't have permission to this transaction"):
            await transaction_service.delete_transaction(existing_transaction.id, other_user)

        transaction_repo_mock.get_by_id.assert_called_once_with(existing_transaction.id)


class TestCreateTransaction:

    async def test_create_transaction_success(
            self,
            existing_currency: Currency,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository
    ):
        data = TransactionCreate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code="UAH",
            description="Foods",
            date=datetime.date(2026, 3, 1),
        )
        owner = 1

        currency_repo_mock.get_by_code.return_value = existing_currency

        created = Transaction(
            id=1,
            type=data.type,
            amount=data.amount,
            currency_code=data.currency_code,
            description=data.description,
            date=data.date,
            user_id=owner
        )
        transaction_repo_mock.create.return_value = created

        actual = await transaction_service.create_transaction(data, owner)

        assert actual == TransactionResponse.model_validate(created)

        call_args = transaction_repo_mock.create.call_args[0][0]
        assert isinstance(call_args, Transaction)
        assert call_args.user_id == owner
        assert call_args.amount == data.amount
        assert call_args.currency_code == data.currency_code

        transaction_repo_mock.create.assert_called_once()

    async def test_create_transaction_not_found_category(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            category_repo_mock: CategoryRepository
    ):
        data = TransactionCreate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code="UAH",
            description="Foods",
            category_id=1,
            date=datetime.date(2026, 3, 1),
        )
        owner = 1

        category_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Category not found"):
            await transaction_service.create_transaction(data, owner)

        transaction_repo_mock.create.assert_not_called()

    async def test_create_transaction_not_found_currency(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
    ):
        data = TransactionCreate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code="UAH",
            description="Foods",
            date=datetime.date(2026, 3, 1),
        )
        owner = 1

        currency_repo_mock.get_by_code.return_value = None

        with pytest.raises(NotFoundException, match="Currency not found"):
            await transaction_service.create_transaction(data, owner)

        transaction_repo_mock.create.assert_not_called()

    async def test_create_transaction_wrong_category_owner(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            category_repo_mock: CategoryRepository
    ):
        data = TransactionCreate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code="UAH",
            description="Foods",
            category_id=1,
            date=datetime.date(2026, 3, 1),
        )
        owner = 1

        category_repo_mock.get_by_id.return_value = Category(name="Foods", user_id=2)

        with pytest.raises(PermissionException, match="You don't have permission to this category"):
            await transaction_service.create_transaction(data, owner)

        transaction_repo_mock.create.assert_not_called()

    async def test_create_transaction_archive_category(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            category_repo_mock: CategoryRepository
    ):
        data = TransactionCreate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code="UAH",
            description="Foods",
            category_id=1,
            date=datetime.date(2026, 3, 1),
        )
        owner = 1

        category_repo_mock.get_by_id.return_value = Category(
            id=1,
            name="Foods",
            user_id=owner,
            archived_at=datetime.datetime.now()
        )

        with pytest.raises(NotAllowedActionException, match="Archived category is not allowed to use"):
            await transaction_service.create_transaction(data, owner)

        transaction_repo_mock.create.assert_not_called()

    async def test_create_transaction_not_active_currency(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
    ):
        data = TransactionCreate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code="UAH",
            description="Foods",
            date=datetime.date(2026, 3, 1),
        )
        owner = 1

        currency_repo_mock.get_by_code.return_value = Currency(
            code="UAH", symbol="₴", name="Ukrainian Hryvnia", is_active=False
        )

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await transaction_service.create_transaction(data, owner)

        transaction_repo_mock.create.assert_not_called()


class TestGetUserTransactions:

    async def test_get_user_existing_transactions(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
    ):
        owner = 1

        user_transactions = [
            Transaction(
                id=1,
                type=TransactionType.EXPENSE,
                amount=Decimal("500.00"),
                currency_code="UAH",
                description="Foods",
                user_id=owner,
                date=datetime.date(2026, 3, 1),
            ),
            Transaction(
                id=2,
                type=TransactionType.INCOME,
                amount=Decimal("20000.00"),
                currency_code="UAH",
                description="Salary",
                user_id=owner,
                date=datetime.date(2026, 3, 1),
            )
        ]

        transaction_repo_mock.get_by_user.return_value = user_transactions

        expected = [
            TransactionResponse.model_validate(t) for t in user_transactions
        ]

        limit = 20
        offset = 0
        filters = TransactionFilters()

        actual = await transaction_service.get_user_transactions(user_id=owner, limit=limit, offset=offset,
                                                                 filters=filters)

        assert actual == expected

        transaction_repo_mock.get_by_user.assert_called_once_with(owner, filters, limit, offset)

    async def test_get_user_empty_transactions(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
    ):
        owner = 1

        user_transactions = []

        transaction_repo_mock.get_by_user.return_value = user_transactions

        expected = [
            TransactionResponse.model_validate(t) for t in user_transactions
        ]

        limit = 20
        offset = 0
        filters = TransactionFilters()

        actual = await transaction_service.get_user_transactions(user_id=owner, limit=limit, offset=offset,
                                                                 filters=filters)

        assert actual == expected

        transaction_repo_mock.get_by_user.assert_called_once_with(owner, filters, limit, offset)


class TestUpdateTransaction:

    async def test_update_transaction_success(
            self,
            existing_transaction: Transaction,
            existing_currency: Currency,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository
    ):
        transaction_repo_mock.get_by_id.return_value = existing_transaction

        data = TransactionUpdate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code=existing_currency.code,
            description="Foods",
            date=datetime.date(2026, 3, 1),
        )

        currency_repo_mock.get_by_code.return_value = existing_currency

        updated = Transaction(
            id=existing_transaction.id,
            type=data.type,
            amount=data.amount,
            currency_code=data.currency_code,
            description=data.description,
            date=data.date,
            user_id=existing_transaction.user_id
        )
        transaction_repo_mock.update.return_value = updated

        actual = await transaction_service.update_transaction(existing_transaction.id, data,
                                                              existing_transaction.user_id)

        assert actual == TransactionResponse.model_validate(updated)

        call_args = transaction_repo_mock.update.call_args[0][0]
        assert isinstance(call_args, Transaction)
        assert call_args.user_id == existing_transaction.user_id
        assert call_args.amount == data.amount
        assert call_args.currency_code == data.currency_code

        transaction_repo_mock.update.assert_called_once()

    async def test_update_transaction_not_found_transaction(
            self,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
    ):
        data = TransactionUpdate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code="UAH",
            description="Foods",
            category_id=1,
            date=datetime.date(2026, 3, 1),
        )
        owner = 1

        transaction_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Transaction not found"):
            await transaction_service.update_transaction(1, data, owner)

        transaction_repo_mock.update.assert_not_called()


    async def test_update_transaction_not_found_category(
            self,
            existing_transaction: Transaction,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            category_repo_mock: CategoryRepository
    ):
        data = TransactionUpdate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code="UAH",
            description="Foods",
            category_id=1,
            date=datetime.date(2026, 3, 1),
        )

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        category_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Category not found"):
            await transaction_service.update_transaction(existing_transaction.id, data, existing_transaction.user_id)

        transaction_repo_mock.update.assert_not_called()

    async def test_update_transaction_not_found_currency(
            self,
            existing_transaction: Transaction,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
    ):
        data = TransactionUpdate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code="UAH",
            description="Foods",
            date=datetime.date(2026, 3, 1),
        )

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        currency_repo_mock.get_by_code.return_value = None

        with pytest.raises(NotFoundException, match="Currency not found"):
            await transaction_service.update_transaction(existing_transaction.id, data, existing_transaction.user_id)

        transaction_repo_mock.update.assert_not_called()

    async def test_update_transaction_wrong_category_owner(
            self,
            existing_transaction: Transaction,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            category_repo_mock: CategoryRepository
    ):
        data = TransactionUpdate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code="UAH",
            description="Foods",
            category_id=1,
            date=datetime.date(2026, 3, 1),
        )

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        category_repo_mock.get_by_id.return_value = Category(name="Foods", user_id=2)

        with pytest.raises(PermissionException, match="You don't have permission to this category"):
            await transaction_service.update_transaction(existing_transaction.id, data, existing_transaction.user_id)

        transaction_repo_mock.update.assert_not_called()


    async def test_update_transaction_wrong_transaction_owner(
            self,
            existing_transaction: Transaction,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
    ):
        data = TransactionUpdate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code="UAH",
            description="Foods",
            date=datetime.date(2026, 3, 1),
        )

        transaction_repo_mock.get_by_id.return_value = existing_transaction

        with pytest.raises(PermissionException, match="You don't have permission to this transaction"):
            await transaction_service.update_transaction(existing_transaction.id, data, 222)

        transaction_repo_mock.update.assert_not_called()

    async def test_update_transaction_archive_category(
            self,
            existing_transaction: Transaction,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            category_repo_mock: CategoryRepository
    ):
        data = TransactionUpdate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code="UAH",
            description="Foods",
            category_id=1,
            date=datetime.date(2026, 3, 1),
        )

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        category_repo_mock.get_by_id.return_value = Category(
            id=1,
            name="Foods",
            user_id=existing_transaction.user_id,
            archived_at=datetime.datetime.now()
        )

        with pytest.raises(NotAllowedActionException, match="Archived category is not allowed to use"):
            await transaction_service.update_transaction(existing_transaction.id, data, existing_transaction.user_id)

        transaction_repo_mock.update.assert_not_called()

    async def test_update_transaction_not_active_currency(
            self,
            existing_transaction: Transaction,
            transaction_service: TransactionService,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
    ):
        data = TransactionUpdate(
            type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency_code="UAH",
            description="Foods",
            date=datetime.date(2026, 3, 1),
        )

        transaction_repo_mock.get_by_id.return_value = existing_transaction
        currency_repo_mock.get_by_code.return_value = Currency(
            code="UAH", symbol="₴", name="Ukrainian Hryvnia", is_active=False
        )

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await transaction_service.update_transaction(existing_transaction.id, data, existing_transaction.user_id)

        transaction_repo_mock.update.assert_not_called()
