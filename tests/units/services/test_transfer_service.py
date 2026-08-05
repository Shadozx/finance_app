import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pytest_mock import MockerFixture

from app.services import TransferService, validators
from app.repositories import TransactionRepository, AccountRepository, CurrencyRepository
from app.models import Transaction, TransactionType, TransactionKind, Account, Currency
from app.schemas import TransferCreate, TransferUpdate
from app.core.exceptions import NotFoundException, NotAllowedActionException
from tests.units.services.helpers import assert_model_fields


@pytest.fixture
def accounts_by_id(
        account_repo_mock: AccountRepository,
        currency_repo_mock: CurrencyRepository,
        existing_account: Account,
        existing_usd_account: Account,
        existing_currency: Currency,
        existing_usd_currency: Currency,
):
    """Both accounts and both currencies are resolvable: create_transfer validates each side."""
    accounts = {
        existing_account.id: existing_account,
        existing_usd_account.id: existing_usd_account,
    }
    currencies = {
        existing_currency.code: existing_currency,
        existing_usd_currency.code: existing_usd_currency,
    }

    account_repo_mock.get_by_id.side_effect = lambda account_id: accounts.get(account_id)
    currency_repo_mock.get_by_code.side_effect = lambda code: currencies.get(code)

    return accounts

@pytest.fixture
def existing_transfer(
        existing_account: Account,
        existing_usd_account: Account,
):
    """A cross-currency transfer pair: 1000 UAH out, 24 USD in."""
    group_id = uuid.uuid4()

    from_side = Transaction(
        id=1,
        type=TransactionType.EXPENSE,
        kind=TransactionKind.TRANSFER,
        amount=Decimal("1000.00"),
        description="Transfer",
        currency_code=existing_account.currency_code,
        user_id=existing_account.user_id,
        category_id=None,
        account_id=existing_account.id,
        transfer_group_id=group_id,
        date=date(2026, 2, 10),
    )

    to_side = Transaction(
        id=2,
        type=TransactionType.INCOME,
        kind=TransactionKind.TRANSFER,
        amount=Decimal("24.00"),
        description="Transfer",
        currency_code=existing_usd_account.currency_code,
        user_id=existing_usd_account.user_id,
        category_id=None,
        account_id=existing_usd_account.id,
        transfer_group_id=group_id,
        date=date(2026, 2, 10),
    )

    return from_side, to_side


class TestCreateTransfer:

    @pytest.fixture
    def data(
            self,
            existing_account: Account,
            existing_usd_account: Account,
    ):
        return TransferCreate(
            from_account_id=existing_account.id,
            to_account_id=existing_usd_account.id,
            from_amount=Decimal("1000.00"),
            to_amount=Decimal("24.00"),
            description="Transfer",
            date=date(2026, 2, 10),
        )

    async def test_create_transfer_success(
            self,
            mocker: MockerFixture,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            accounts_by_id,
            existing_account: Account,
            existing_usd_account: Account,
            data: TransferCreate,
    ):
        user_id = existing_account.user_id

        validate_account_spy = mocker.spy(validators, "validate_account")

        result = await transfer_service.create_transfer(data, user_id)

        assert transaction_repo_mock.add.call_count == 2

        from_side = transaction_repo_mock.add.call_args_list[0][0][0]
        to_side = transaction_repo_mock.add.call_args_list[1][0][0]

        assert_model_fields(
            from_side,
            type=TransactionType.EXPENSE,
            kind=TransactionKind.TRANSFER,
            amount=data.from_amount,
            currency_code=existing_account.currency_code,
            account_id=existing_account.id,
            category_id=None,
            user_id=user_id,
            description=data.description,
            date=data.date,
        )

        assert_model_fields(
            to_side,
            type=TransactionType.INCOME,
            kind=TransactionKind.TRANSFER,
            amount=data.to_amount,
            currency_code=existing_usd_account.currency_code,
            account_id=existing_usd_account.id,
            category_id=None,
            user_id=user_id,
            description=data.description,
            date=data.date,
        )

        assert from_side.transfer_group_id == to_side.transfer_group_id
        assert from_side.transfer_group_id is not None

        assert result.transfer_group_id == from_side.transfer_group_id
        assert result.from_account_id == existing_account.id
        assert result.to_account_id == existing_usd_account.id
        assert result.exchange_rate is not None

        assert validate_account_spy.call_count == 2

        transaction_repo_mock.commit.assert_called_once()

    async def test_create_transfer_same_currency_equal_amounts_success(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            accounts_by_id,
            existing_account: Account,
            existing_usd_account: Account,
            data: TransferCreate,
    ):
        existing_usd_account.currency_code = existing_account.currency_code

        data.to_amount = data.from_amount

        result = await transfer_service.create_transfer(data, existing_account.user_id)

        assert result.exchange_rate is None

        assert transaction_repo_mock.add.call_count == 2

        transaction_repo_mock.commit.assert_called_once()

    async def test_create_transfer_same_currency_different_amounts_rejected(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            accounts_by_id,
            existing_account: Account,
            existing_usd_account: Account,
            data: TransferCreate,
    ):
        existing_usd_account.currency_code = existing_account.currency_code

        with pytest.raises(
                NotAllowedActionException,
                match="Transfer between accounts in the same currency must have equal amounts",
        ):
            await transfer_service.create_transfer(data, existing_account.user_id)

        transaction_repo_mock.add.assert_not_called()

        transaction_repo_mock.commit.assert_not_called()

    async def test_create_transfer_not_found_account(
            self,
            transfer_service: TransferService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            data: TransferCreate,
    ):
        account_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Account not found"):
            await transfer_service.create_transfer(data, 1)

        transaction_repo_mock.add.assert_not_called()

        transaction_repo_mock.commit.assert_not_called()

    async def test_create_transfer_archived_source_account_rejected(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            accounts_by_id,
            existing_account: Account,
            data: TransferCreate,
    ):
        existing_account.archived_at = datetime.now(timezone.utc)

        with pytest.raises(NotAllowedActionException, match="Archived account is not allowed to use"):
            await transfer_service.create_transfer(data, existing_account.user_id)

        transaction_repo_mock.add.assert_not_called()

    async def test_create_transfer_archived_target_account_rejected(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            accounts_by_id,
            existing_account: Account,
            existing_usd_account: Account,
            data: TransferCreate,
    ):
        existing_usd_account.archived_at = datetime.now(timezone.utc)

        with pytest.raises(NotAllowedActionException, match="Archived account is not allowed to use"):
            await transfer_service.create_transfer(data, existing_account.user_id)

        transaction_repo_mock.add.assert_not_called()

    async def test_create_transfer_inactive_source_currency_rejected(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            accounts_by_id,
            existing_account: Account,
            existing_currency: Currency,
            data: TransferCreate,
    ):
        existing_currency.is_active = False

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await transfer_service.create_transfer(data, existing_account.user_id)

        transaction_repo_mock.add.assert_not_called()

    async def test_create_transfer_inactive_target_currency_rejected(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            accounts_by_id,
            existing_account: Account,
            existing_usd_currency: Currency,
            data: TransferCreate,
    ):
        existing_usd_currency.is_active = False

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await transfer_service.create_transfer(data, existing_account.user_id)

        transaction_repo_mock.add.assert_not_called()


class TestGetTransfer:

    async def test_get_transfer_success(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            accounts_by_id,
            existing_account: Account,
            existing_usd_account: Account,
            existing_transfer,
    ):
        from_side, to_side = existing_transfer
        group_id = from_side.transfer_group_id

        transaction_repo_mock.get_by_transfer_group.return_value = [from_side, to_side]

        result = await transfer_service.get_transfer(group_id, existing_account.user_id)

        assert result.transfer_group_id == group_id
        assert result.from_account_id == existing_account.id
        assert result.to_account_id == existing_usd_account.id
        assert result.from_amount == from_side.amount
        assert result.to_amount == to_side.amount

        transaction_repo_mock.get_by_transfer_group.assert_called_once_with(
            group_id, existing_account.user_id
        )

    async def test_get_transfer_not_found(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
    ):
        transaction_repo_mock.get_by_transfer_group.return_value = []

        with pytest.raises(NotFoundException, match="Transfer not found"):
            await transfer_service.get_transfer(uuid.uuid4(), 1)

    async def test_get_transfer_orphan_side_not_found(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            existing_transfer,
    ):
        """A group with a single row is not a transfer: it cannot be shown as a pair."""
        from_side, _ = existing_transfer

        transaction_repo_mock.get_by_transfer_group.return_value = [from_side]

        with pytest.raises(NotFoundException, match="Transfer not found"):
            await transfer_service.get_transfer(from_side.transfer_group_id, from_side.user_id)


class TestUpdateTransfer:

    @pytest.fixture
    def data(
            self,
            existing_account: Account,
            existing_usd_account: Account,
    ):
        return TransferUpdate(
            from_account_id=existing_account.id,
            to_account_id=existing_usd_account.id,
            from_amount=Decimal("2000.00"),
            to_amount=Decimal("48.00"),
            description="Updated transfer",
            date=date(2026, 3, 1),
        )

    async def test_update_transfer_success(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            accounts_by_id,
            existing_account: Account,
            existing_usd_account: Account,
            existing_transfer,
            data: TransferUpdate,
    ):
        from_side, to_side = existing_transfer

        transaction_repo_mock.get_by_transfer_group.return_value = [from_side, to_side]

        result = await transfer_service.update_transfer(
            from_side.transfer_group_id, data, existing_account.user_id
        )

        assert from_side.amount == data.from_amount
        assert from_side.type == TransactionType.EXPENSE
        assert from_side.account_id == existing_account.id
        assert from_side.date == data.date

        assert to_side.amount == data.to_amount
        assert to_side.type == TransactionType.INCOME
        assert to_side.account_id == existing_usd_account.id

        assert result.from_amount == data.from_amount
        assert result.to_amount == data.to_amount

        transaction_repo_mock.commit.assert_called_once()

    async def test_update_transfer_swapped_directions_rewrites_both_sides(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            accounts_by_id,
            existing_account: Account,
            existing_usd_account: Account,
            existing_transfer,
            data: TransferUpdate,
    ):
        """Swapping from/to must not leave two EXPENSE rows in one group."""
        from_side, to_side = existing_transfer

        data.from_account_id = existing_usd_account.id
        data.to_account_id = existing_account.id

        transaction_repo_mock.get_by_transfer_group.return_value = [from_side, to_side]

        await transfer_service.update_transfer(
            from_side.transfer_group_id, data, existing_account.user_id
        )

        assert from_side.type == TransactionType.EXPENSE
        assert from_side.account_id == existing_usd_account.id
        assert from_side.currency_code == existing_usd_account.currency_code

        assert to_side.type == TransactionType.INCOME
        assert to_side.account_id == existing_account.id
        assert to_side.currency_code == existing_account.currency_code

    async def test_update_transfer_keeps_archived_account_allowed(
            self,
            mocker: MockerFixture,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            accounts_by_id,
            existing_account: Account,
            existing_transfer,
            data: TransferUpdate,
    ):
        """Editing amounts of a transfer whose account was archived later must stay possible."""
        existing_account.archived_at = datetime.now(timezone.utc)

        from_side, to_side = existing_transfer

        transaction_repo_mock.get_by_transfer_group.return_value = [from_side, to_side]

        validate_account_spy = mocker.spy(validators, "validate_account")

        await transfer_service.update_transfer(
            from_side.transfer_group_id, data, existing_account.user_id
        )

        assert validate_account_spy.call_args_list[0].kwargs["allow_archived"] is True

        transaction_repo_mock.commit.assert_called_once()

    async def test_update_transfer_to_archived_account_rejected(
            self,
            transfer_service: TransferService,
            account_repo_mock: AccountRepository,
            transaction_repo_mock: TransactionRepository,
            existing_account: Account,
            existing_usd_account: Account,
            existing_transfer,
            data: TransferUpdate,
    ):
        """Moving a transfer TO an account that is not part of it and is archived → 409."""
        archived_account = Account(
            id=3,
            name="Closed card",
            currency_code=existing_usd_account.currency_code,
            user_id=existing_account.user_id,
            created_at=datetime(2026, 2, 10, tzinfo=timezone.utc),
            archived_at=datetime.now(timezone.utc),
        )

        accounts = {
            existing_account.id: existing_account,
            existing_usd_account.id: existing_usd_account,
            archived_account.id: archived_account,
        }
        account_repo_mock.get_by_id.side_effect = lambda account_id: accounts.get(account_id)

        data.to_account_id = archived_account.id

        from_side, to_side = existing_transfer

        transaction_repo_mock.get_by_transfer_group.return_value = [from_side, to_side]

        with pytest.raises(NotAllowedActionException, match="Archived account is not allowed to use"):
            await transfer_service.update_transfer(
                from_side.transfer_group_id, data, existing_account.user_id
            )

        transaction_repo_mock.commit.assert_not_called()

    async def test_update_transfer_not_found(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            data: TransferUpdate,
    ):
        transaction_repo_mock.get_by_transfer_group.return_value = []

        with pytest.raises(NotFoundException, match="Transfer not found"):
            await transfer_service.update_transfer(uuid.uuid4(), data, 1)

        transaction_repo_mock.commit.assert_not_called()

    async def test_update_transfer_keeps_inactive_currency_allowed(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            accounts_by_id,
            existing_account: Account,
            existing_currency: Currency,
            existing_transfer,
            data: TransferUpdate,
    ):
        """Editing a transfer whose currency was deactivated later must stay possible."""
        existing_currency.is_active = False

        from_side, to_side = existing_transfer

        transaction_repo_mock.get_by_transfer_group.return_value = [from_side, to_side]

        await transfer_service.update_transfer(
            from_side.transfer_group_id, data, existing_account.user_id
        )

        transaction_repo_mock.commit.assert_called_once()


class TestDeleteTransfer:

    async def test_delete_transfer_success(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
            existing_transfer,
    ):
        from_side, to_side = existing_transfer
        group_id = from_side.transfer_group_id

        transaction_repo_mock.get_by_transfer_group.return_value = [from_side, to_side]

        await transfer_service.delete_transfer(group_id, from_side.user_id)

        transaction_repo_mock.delete_by_transfer_group.assert_called_once_with(
            group_id, from_side.user_id
        )

    async def test_delete_transfer_not_found(
            self,
            transfer_service: TransferService,
            transaction_repo_mock: TransactionRepository,
    ):
        transaction_repo_mock.get_by_transfer_group.return_value = []

        with pytest.raises(NotFoundException, match="Transfer not found"):
            await transfer_service.delete_transfer(uuid.uuid4(), 1)

        transaction_repo_mock.delete_by_transfer_group.assert_not_called()