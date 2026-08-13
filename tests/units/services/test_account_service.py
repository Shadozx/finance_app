from datetime import datetime, timezone

from decimal import Decimal

import pytest
from pytest_mock import MockerFixture

from app.core import UnitOfWork
from app.models import Account, Currency, TransactionType, TransactionKind
from app.repositories import AccountRepository, CurrencyRepository, TransactionRepository
from app.services import AccountService, validators
from app.schemas import AccountCreate, AccountUpdate, AccountResponse, AccountStatus, InitialBalanceKind, \
    AccountReconcile, AccountReconcileResponse
from app.core.exceptions import (
    NotFoundException,
    ValueExistsException,
    NotAllowedActionException,
    PermissionException,
)
from tests.units.services.helpers import assert_model_fields


def to_response(account: Account, balance: Decimal) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        name=account.name,
        currency_code=account.currency_code,
        balance=balance,
        archived_at=account.archived_at,
        created_at=account.created_at,
        user_id=account.user_id,
    )


class TestCreateAccount:

    @pytest.fixture
    def data(self, existing_currency: Currency):
        return AccountCreate(
            name="Cash",
            currency_code=existing_currency.code,
        )

    async def test_create_account_success(
            self,
            mocker: MockerFixture,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
            unit_of_work_mock: UnitOfWork,
            existing_currency: Currency,
            data: AccountCreate,
    ):
        user_id = 1

        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_user_and_name.return_value = None
        transaction_repo_mock.get_balance.return_value = Decimal("0")

        created = Account(
            id=1,
            name=data.name,
            currency_code=data.currency_code,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            archived_at=None,
        )
        account_repo_mock.add.return_value = created

        validate_currency_spy = mocker.spy(validators, "validate_currency")

        result = await account_service.create_account(data, user_id)

        assert result == to_response(created, Decimal("0"))

        call_args = account_repo_mock.add.call_args[0][0]
        assert_model_fields(
            call_args,
            name=data.name,
            currency_code=data.currency_code,
            user_id=user_id,
        )

        validate_currency_spy.assert_called_once_with(
            account_service.currency_repository,
            data.currency_code,
        )

        account_repo_mock.get_by_user_and_name.assert_called_once_with(
            user_id,
            data.name,
        )

        account_repo_mock.add.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

        transaction_repo_mock.get_balance.assert_not_called()

    async def test_create_account_with_positive_existing_balance(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
            unit_of_work_mock: UnitOfWork,
            existing_currency: Currency,
            data: AccountCreate,
    ):
        user_id = 1
        data.initial_balance = Decimal("5000.00")
        data.initial_balance_kind = InitialBalanceKind.EXISTING

        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_user_and_name.return_value = None

        created = Account(
            id=1,
            name=data.name,
            currency_code=data.currency_code,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            archived_at=None,
        )
        account_repo_mock.add.return_value = created

        result = await account_service.create_account(data, user_id)

        assert result.balance == Decimal("5000.00")

        call_args = transaction_repo_mock.add.call_args[0][0]
        assert_model_fields(
            call_args,
            type=TransactionType.INCOME,
            kind=TransactionKind.ADJUSTMENT,
            amount=Decimal("5000.00"),
            currency_code=data.currency_code,
            account_id=created.id,
            user_id=user_id,
        )

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_create_account_with_positive_received_balance(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
            existing_currency: Currency,
            data: AccountCreate,
    ):
        user_id = 1
        data.initial_balance = Decimal("5000.00")
        data.initial_balance_kind = InitialBalanceKind.RECEIVED

        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_user_and_name.return_value = None

        created = Account(
            id=1,
            name=data.name,
            currency_code=data.currency_code,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
        )
        account_repo_mock.add.return_value = created

        await account_service.create_account(data, user_id)

        call_args = transaction_repo_mock.add.call_args[0][0]
        assert_model_fields(
            call_args,
            type=TransactionType.INCOME,
            kind=TransactionKind.REGULAR,
            amount=Decimal("5000.00"),
        )

    async def test_create_account_with_negative_balance_creates_expense(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
            existing_currency: Currency,
            data: AccountCreate,
    ):
        user_id = 1
        data.initial_balance = Decimal("-2000.00")
        data.initial_balance_kind = InitialBalanceKind.EXISTING

        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_user_and_name.return_value = None

        created = Account(
            id=1,
            name=data.name,
            currency_code=data.currency_code,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
        )
        account_repo_mock.add.return_value = created

        result = await account_service.create_account(data, user_id)

        assert result.balance == Decimal("-2000.00")

        call_args = transaction_repo_mock.add.call_args[0][0]
        assert_model_fields(
            call_args,
            type=TransactionType.EXPENSE,
            kind=TransactionKind.ADJUSTMENT,
            amount=Decimal("2000.00"),
        )

    async def test_create_account_with_zero_balance_creates_no_transaction(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
            unit_of_work_mock: UnitOfWork,
            existing_currency: Currency,
            data: AccountCreate,
    ):
        user_id = 1
        data.initial_balance = Decimal("0")

        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_user_and_name.return_value = None

        created = Account(
            id=1,
            name=data.name,
            currency_code=data.currency_code,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
        )
        account_repo_mock.add.return_value = created

        result = await account_service.create_account(data, user_id)

        assert result.balance == Decimal("0")

        transaction_repo_mock.add.assert_not_called()
        unit_of_work_mock.commit.assert_awaited_once()

    async def test_create_account_duplicate_name(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            currency_repo_mock: CurrencyRepository,
            unit_of_work_mock: UnitOfWork,
            existing_account: Account,
            existing_currency: Currency,
            data: AccountCreate,
    ):
        data.name = existing_account.name
        user_id = existing_account.user_id

        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_user_and_name.return_value = existing_account

        with pytest.raises(ValueExistsException, match="Account with this name exists"):
            await account_service.create_account(data, user_id)

        account_repo_mock.add.assert_not_called()
        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_account_unknown_currency(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            currency_repo_mock: CurrencyRepository,
            unit_of_work_mock: UnitOfWork,
            data: AccountCreate,
    ):
        user_id = 1

        account_repo_mock.get_by_user_and_name.return_value = None
        currency_repo_mock.get_by_code.return_value = None

        with pytest.raises(NotFoundException, match="Currency not found"):
            await account_service.create_account(data, user_id)

        account_repo_mock.add.assert_not_called()
        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_account_inactive_currency(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            currency_repo_mock: CurrencyRepository,
            unit_of_work_mock: UnitOfWork,
            existing_currency: Currency,
            data: AccountCreate,
    ):
        user_id = 1
        account_repo_mock.get_by_user_and_name.return_value = None
        existing_currency.is_active = False

        currency_repo_mock.get_by_code.return_value = existing_currency

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await account_service.create_account(data, user_id)

        account_repo_mock.add.assert_not_called()
        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_account_balance_transaction_fails_nothing_committed(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            currency_repo_mock: CurrencyRepository,
            unit_of_work_mock: UnitOfWork,
            existing_account: Account,
            existing_currency: Currency,
            data: AccountCreate,
    ):
        """Both sides belong to one operation: if the second fails, the first must not be committed."""
        user_id = existing_account.user_id

        data.initial_balance = Decimal("5000.00")
        data.initial_balance_kind = InitialBalanceKind.EXISTING

        currency_repo_mock.get_by_code.return_value = existing_currency
        account_repo_mock.get_by_user_and_name.return_value = None

        created = Account(
            id=1,
            name=data.name,
            currency_code=data.currency_code,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
        )
        account_repo_mock.add.return_value = created

        transaction_repo_mock.add.side_effect = RuntimeError("db error")

        with pytest.raises(RuntimeError):
            await account_service.create_account(data, user_id)

        account_repo_mock.add.assert_called_once()
        transaction_repo_mock.add.assert_called_once()

        unit_of_work_mock.commit.assert_not_awaited()


class TestGetAccount:
    async def test_get_account_success(
            self,
            mocker: MockerFixture,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            existing_account: Account,
    ):
        account_repo_mock.get_by_id.return_value = existing_account
        transaction_repo_mock.get_balance.return_value = Decimal("150")

        validate_account_spy = mocker.spy(validators, "validate_account")

        result = await account_service.get_account(
            existing_account.id,
            existing_account.user_id,
        )

        assert result == to_response(existing_account, Decimal("150"))

        validate_account_spy.assert_called_once_with(
            account_service.account_repository,
            existing_account.user_id,
            existing_account.id,
            allow_archived=True,
        )

        transaction_repo_mock.get_balance.assert_called_once_with(
            existing_account.id
        )

    async def test_get_account_not_found(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
    ):
        account_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Account not found"):
            await account_service.get_account(999, 1)

    async def test_get_account_wrong_owner(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            existing_account: Account,
    ):
        wrong_user_id = existing_account.user_id + 1

        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(PermissionException, match="You don't have permission to this account"):
            await account_service.get_account(existing_account.id, wrong_user_id)

    async def test_get_account_archived_allowed(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            existing_account: Account,
    ):
        existing_account.archived_at = datetime.now(timezone.utc)

        account_repo_mock.get_by_id.return_value = existing_account
        transaction_repo_mock.get_balance.return_value = Decimal("150")

        result = await account_service.get_account(
            existing_account.id,
            existing_account.user_id,
        )

        assert result.id == existing_account.id
        assert result.archived_at is not None


class TestGetUserAccounts:
    async def test_get_user_accounts_success(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            existing_currency: Currency,
    ):
        user_id = 1
        balances = {1: Decimal("0"), 2: Decimal("150")}
        transaction_repo_mock.get_balances_by_account.return_value = balances

        user_accounts = [
            Account(
                id=1,
                name="Monobank",
                currency_code=existing_currency.code,
                user_id=user_id,
                created_at=datetime.now(timezone.utc),
            ),
            Account(
                id=2,
                name="Cash",
                currency_code=existing_currency.code,
                user_id=user_id,
                created_at=datetime.now(timezone.utc),
            ),
        ]

        account_repo_mock.get_by_user.return_value = user_accounts

        result = await account_service.get_user_accounts(user_id)

        assert result == [to_response(a, balance=balances.get(a.id, Decimal("0"))) for a in user_accounts]

        account_repo_mock.get_by_user.assert_called_once_with(
            user_id=user_id,
            status=AccountStatus.ACTIVE,
        )

        transaction_repo_mock.get_balances_by_account.assert_called_once_with(
            user_id
        )

    async def test_get_user_accounts_empty(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
    ):
        user_id = 1

        account_repo_mock.get_by_user.return_value = []
        transaction_repo_mock.get_balances_by_account.return_value = {}

        result = await account_service.get_user_accounts(user_id)

        assert result == []

        account_repo_mock.get_by_user.assert_called_once_with(
            user_id=user_id,
            status=AccountStatus.ACTIVE,
        )

    async def test_get_user_accounts_passes_status(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
    ):
        user_id = 1

        account_repo_mock.get_by_user.return_value = []
        transaction_repo_mock.get_balances_by_account.return_value = {}

        await account_service.get_user_accounts(user_id, AccountStatus.ALL)

        account_repo_mock.get_by_user.assert_called_once_with(
            user_id=user_id,
            status=AccountStatus.ALL,
        )


class TestUpdateAccount:

    @pytest.fixture
    def data(self):
        return AccountUpdate(name="Renamed Account")

    async def test_update_account_success(
            self,
            mocker: MockerFixture,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            unit_of_work_mock: UnitOfWork,
            existing_account: Account,
            data: AccountUpdate,
    ):
        user_id = existing_account.user_id
        balance = Decimal("150")

        account_repo_mock.get_by_id.return_value = existing_account
        account_repo_mock.get_by_user_and_name.return_value = None
        transaction_repo_mock.get_balance.return_value = balance

        updated = Account(
            id=existing_account.id,
            name=data.name,
            currency_code=existing_account.currency_code,
            user_id=user_id,
            created_at=existing_account.created_at,
        )
        account_repo_mock.update.return_value = updated

        validate_account_spy = mocker.spy(validators, "validate_account")

        result = await account_service.update_account(
            existing_account.id,
            data,
            user_id,
        )

        assert result == to_response(updated, balance)

        call_args = account_repo_mock.update.call_args[0][0]
        assert_model_fields(
            call_args,
            name=data.name,
            user_id=user_id,
        )

        validate_account_spy.assert_called_once_with(
            account_service.account_repository,
            user_id,
            existing_account.id,
            allow_archived=True,
        )

        account_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

        transaction_repo_mock.get_balance.assert_called_once_with(
            existing_account.id,
        )

    async def test_update_account_does_not_change_currency(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            existing_account: Account,
            data: AccountUpdate,
    ):
        original_currency = existing_account.currency_code

        account_repo_mock.get_by_id.return_value = existing_account
        account_repo_mock.get_by_user_and_name.return_value = None
        account_repo_mock.update.return_value = existing_account
        transaction_repo_mock.get_balance.return_value = Decimal("0")

        await account_service.update_account(
            existing_account.id,
            data,
            existing_account.user_id,
        )

        call_args = account_repo_mock.update.call_args[0][0]

        assert call_args.currency_code == original_currency

    async def test_update_account_archived_allowed(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            existing_account: Account,
            data: AccountUpdate,
    ):
        existing_account.archived_at = datetime.now(timezone.utc)

        account_repo_mock.get_by_id.return_value = existing_account
        account_repo_mock.get_by_user_and_name.return_value = None
        account_repo_mock.update.return_value = existing_account
        transaction_repo_mock.get_balance.return_value = Decimal("0")

        result = await account_service.update_account(
            existing_account.id,
            data,
            existing_account.user_id,
        )

        assert result.name == data.name

        account_repo_mock.update.assert_called_once()

    async def test_update_account_not_found(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            data: AccountUpdate,
    ):
        account_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Account not found"):
            await account_service.update_account(999, data, 1)

        account_repo_mock.update.assert_not_called()

    async def test_update_account_wrong_owner(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            existing_account: Account,
            data: AccountUpdate,
    ):
        wrong_user_id = existing_account.user_id + 1

        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(PermissionException, match="You don't have permission to this account"):
            await account_service.update_account(
                existing_account.id,
                data,
                wrong_user_id,
            )

        account_repo_mock.update.assert_not_called()

    async def test_update_account_duplicate_name(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            existing_account: Account,
            existing_currency: Currency,
            data: AccountUpdate,
    ):
        account_repo_mock.get_by_id.return_value = existing_account

        duplicate = Account(
            id=existing_account.id + 1,
            name=data.name,
            currency_code=existing_currency.code,
            user_id=existing_account.user_id,
            created_at=datetime.now(timezone.utc),
        )
        account_repo_mock.get_by_user_and_name.return_value = duplicate

        with pytest.raises(ValueExistsException, match="Account with this name exists"):
            await account_service.update_account(
                existing_account.id,
                data,
                existing_account.user_id,
            )

        account_repo_mock.update.assert_not_called()

    async def test_update_account_same_name_allowed(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            existing_account: Account,
            data: AccountUpdate,
    ):
        data.name = existing_account.name

        account_repo_mock.get_by_id.return_value = existing_account
        account_repo_mock.get_by_user_and_name.return_value = existing_account
        account_repo_mock.update.return_value = existing_account
        transaction_repo_mock.get_balance.return_value = Decimal("0")

        result = await account_service.update_account(
            existing_account.id,
            data,
            existing_account.user_id,
        )

        assert result.name == existing_account.name

        account_repo_mock.update.assert_called_once()


class TestArchiveAccount:
    async def test_archive_account_success(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            unit_of_work_mock: UnitOfWork,
            existing_account: Account,
    ):
        account_repo_mock.get_by_id.return_value = existing_account

        await account_service.archive_account(
            existing_account.id,
            existing_account.user_id,
        )

        account_repo_mock.archive.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_archive_account_not_found(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            unit_of_work_mock: UnitOfWork,
    ):
        account_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Account not found"):
            await account_service.archive_account(999, 1)

        account_repo_mock.archive.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_archive_account_wrong_owner(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            existing_account: Account,
    ):
        wrong_user_id = existing_account.user_id + 1

        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(PermissionException, match="You don't have permission to this account"):
            await account_service.archive_account(existing_account.id, wrong_user_id)

        account_repo_mock.archive.assert_not_called()

    async def test_archive_account_already_archived(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            existing_account: Account,
    ):
        existing_account.archived_at = datetime.now(timezone.utc)

        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(NotAllowedActionException, match="Account is archived"):
            await account_service.archive_account(
                existing_account.id,
                existing_account.user_id,
            )

        account_repo_mock.archive.assert_not_called()


class TestRestoreAccount:
    async def test_restore_account_success(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            unit_of_work_mock: UnitOfWork,
            existing_account: Account,
    ):
        existing_account.archived_at = datetime.now(timezone.utc)

        account_repo_mock.get_by_id.return_value = existing_account
        account_repo_mock.get_by_user_and_name.return_value = existing_account
        transaction_repo_mock.get_balance.return_value = Decimal("0")

        result = await account_service.restore_account(
            existing_account.id,
            existing_account.user_id,
        )

        assert result == to_response(existing_account, Decimal("0"))

        call_args = account_repo_mock.restore.call_args[0][0]
        assert_model_fields(
            call_args,
            name=existing_account.name,
            currency_code=existing_account.currency_code,
            user_id=existing_account.user_id,
        )
        account_repo_mock.restore.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

        transaction_repo_mock.get_balance.assert_called_once_with(
            existing_account.id,
        )

    async def test_restore_account_not_found(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            unit_of_work_mock: UnitOfWork,
    ):
        account_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Account not found"):
            await account_service.restore_account(999, 1)

        account_repo_mock.restore.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_restore_account_wrong_owner(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            existing_account: Account,
    ):
        existing_account.archived_at = datetime.now(timezone.utc)
        wrong_user_id = existing_account.user_id + 1

        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(PermissionException, match="You don't have permission to this account"):
            await account_service.restore_account(existing_account.id, wrong_user_id)

        account_repo_mock.restore.assert_not_called()

    async def test_restore_account_not_archived(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            existing_account: Account,
    ):
        account_repo_mock.get_by_id.return_value = existing_account

        with pytest.raises(NotAllowedActionException, match="Account is not archived"):
            await account_service.restore_account(
                existing_account.id,
                existing_account.user_id,
            )

        account_repo_mock.restore.assert_not_called()

    async def test_restore_account_duplicate_active_name(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            existing_account: Account,
            existing_currency: Currency,
    ):
        existing_account.archived_at = datetime.now(timezone.utc)

        active_duplicate = Account(
            id=existing_account.id + 1,
            name=existing_account.name,
            currency_code=existing_currency.code,
            user_id=existing_account.user_id,
            created_at=datetime.now(timezone.utc),
            archived_at=None,
        )

        account_repo_mock.get_by_id.return_value = existing_account
        account_repo_mock.get_by_user_and_name.return_value = active_duplicate

        with pytest.raises(ValueExistsException, match="Active account with this name already exists"):
            await account_service.restore_account(
                existing_account.id,
                existing_account.user_id,
            )

        account_repo_mock.restore.assert_not_called()


class TestReconcileAccount:
    async def test_reconcile_account_positive_difference(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            unit_of_work_mock: UnitOfWork,
            existing_account: Account,
    ):
        account_repo_mock.get_by_id.return_value = existing_account
        transaction_repo_mock.get_balance.return_value = Decimal("4700.00")

        data = AccountReconcile(actual_balance=Decimal("5000.00"))

        result = await account_service.reconcile_account(
            existing_account.id,
            data,
            existing_account.user_id,
        )

        assert result.adjusted is True
        assert result.difference == Decimal("300.00")
        assert result.account.balance == Decimal("5000.00")

        call_args = transaction_repo_mock.add.call_args[0][0]
        assert_model_fields(
            call_args,
            type=TransactionType.INCOME,
            kind=TransactionKind.ADJUSTMENT,
            amount=Decimal("300.00"),
            currency_code=existing_account.currency_code,
            account_id=existing_account.id,
            user_id=existing_account.user_id,
            category_id=None,
        )

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_reconcile_account_negative_difference(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            existing_account: Account,
    ):
        account_repo_mock.get_by_id.return_value = existing_account
        transaction_repo_mock.get_balance.return_value = Decimal("5000.00")

        data = AccountReconcile(actual_balance=Decimal("4700.00"))

        result = await account_service.reconcile_account(
            existing_account.id,
            data,
            existing_account.user_id,
        )

        assert result.adjusted is True
        assert result.difference == Decimal("-300.00")
        assert result.account.balance == Decimal("4700.00")

        call_args = transaction_repo_mock.add.call_args[0][0]
        assert_model_fields(
            call_args,
            type=TransactionType.EXPENSE,
            kind=TransactionKind.ADJUSTMENT,
            amount=Decimal("300.00"),
        )

    async def test_reconcile_account_no_difference_creates_nothing(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            unit_of_work_mock: UnitOfWork,
            existing_account: Account,
    ):
        account_repo_mock.get_by_id.return_value = existing_account
        transaction_repo_mock.get_balance.return_value = Decimal("5000.00")

        data = AccountReconcile(actual_balance=Decimal("5000.00"))

        result = await account_service.reconcile_account(
            existing_account.id,
            data,
            existing_account.user_id,
        )

        assert result.adjusted is False
        assert result.difference == Decimal("0")
        assert result.account.balance == Decimal("5000.00")

        transaction_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_reconcile_account_to_zero(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            existing_account: Account,
    ):
        account_repo_mock.get_by_id.return_value = existing_account
        transaction_repo_mock.get_balance.return_value = Decimal("500.00")

        data = AccountReconcile(actual_balance=Decimal("0"))

        result = await account_service.reconcile_account(
            existing_account.id,
            data,
            existing_account.user_id,
        )

        assert result.adjusted is True
        assert result.difference == Decimal("-500.00")
        assert result.account.balance == Decimal("0")

    async def test_reconcile_account_archived_fails(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            unit_of_work_mock: UnitOfWork,
            existing_account: Account,
    ):
        existing_account.archived_at = datetime.now(timezone.utc)

        account_repo_mock.get_by_id.return_value = existing_account

        data = AccountReconcile(actual_balance=Decimal("5000.00"))

        with pytest.raises(NotAllowedActionException, match="Archived account is not allowed to use"):
            await account_service.reconcile_account(
                existing_account.id,
                data,
                existing_account.user_id,
            )

        transaction_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_reconcile_account_not_found(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
    ):
        account_repo_mock.get_by_id.return_value = None

        data = AccountReconcile(actual_balance=Decimal("5000.00"))

        with pytest.raises(NotFoundException, match="Account not found"):
            await account_service.reconcile_account(999, data, 1)

        transaction_repo_mock.add.assert_not_called()

    async def test_reconcile_account_wrong_owner(
            self,
            account_service: AccountService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            existing_account: Account,
    ):
        wrong_user_id = existing_account.user_id + 1

        account_repo_mock.get_by_id.return_value = existing_account

        data = AccountReconcile(actual_balance=Decimal("5000.00"))

        with pytest.raises(PermissionException, match="You don't have permission to this account"):
            await account_service.reconcile_account(
                existing_account.id,
                data,
                wrong_user_id,
            )

        transaction_repo_mock.add.assert_not_called()
