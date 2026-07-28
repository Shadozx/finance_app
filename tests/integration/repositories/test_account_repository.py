from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.repositories import UserRepository, AccountRepository
from app.models import User, Account, Currency
from app.schemas import AccountStatus


@pytest.fixture
async def account(
        account_repository: AccountRepository,
        user: User,
        uah_currency: Currency,
):
    return await account_repository.create(Account(
        name="Monobank",
        currency_code=uah_currency.code,
        user_id=user.id,
    ))


@pytest.fixture
async def archived_account(
        account_repository: AccountRepository,
        user: User,
        uah_currency: Currency,
):
    return await account_repository.create(Account(
        name="Closed Card",
        currency_code=uah_currency.code,
        user_id=user.id,
        archived_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    ))


class TestCreate:

    async def test_create(
            self,
            account_repository: AccountRepository,
            user: User,
            uah_currency: Currency,
    ):
        new_account = Account(
            name="Cash",
            currency_code=uah_currency.code,
            user_id=user.id,
        )

        created_account = await account_repository.create(new_account)

        assert created_account.id is not None
        assert created_account.name == new_account.name
        assert created_account.currency_code == new_account.currency_code
        assert created_account.user_id == new_account.user_id
        assert created_account.created_at is not None
        assert created_account.archived_at is None

    async def test_create_duplicate_name_same_user(
            self,
            account_repository: AccountRepository,
            account: Account,
            usd_currency: Currency,
    ):
        duplicate_account = Account(
            name=account.name,
            currency_code=usd_currency.code,
            user_id=account.user_id,
        )

        with pytest.raises(IntegrityError):
            await account_repository.create(duplicate_account)

    async def test_create_same_name_for_different_users_allowed(
            self,
            test_session: AsyncSession,
            account_repository: AccountRepository,
            account: Account,
            uah_currency: Currency,
    ):
        other_user_repository = UserRepository(test_session)
        other_user = await other_user_repository.create(User(
            email="other@test.com",
            username="other",
            hashed_password="hashed",
        ))

        other_account = await account_repository.create(Account(
            name=account.name,
            currency_code=uah_currency.code,
            user_id=other_user.id,
        ))

        assert other_account.id != account.id
        assert other_account.name == account.name


class TestGetById:
    async def test_get_by_id(
            self,
            account_repository: AccountRepository,
            account: Account,
    ):
        found_account = await account_repository.get_by_id(account.id)

        assert found_account.id == account.id
        assert found_account.name == account.name
        assert found_account.currency_code == account.currency_code

    async def test_get_by_id_not_found(
            self,
            account_repository: AccountRepository,
    ):
        found_account = await account_repository.get_by_id(999)

        assert found_account is None


class TestGetByUser:
    async def test_get_by_user_default_returns_active_accounts(
            self,
            account_repository: AccountRepository,
            account: Account,
            usd_currency: Currency,
    ):
        new_account = await account_repository.create(Account(
            name="Dollars",
            currency_code=usd_currency.code,
            user_id=account.user_id,
        ))

        accounts = await account_repository.get_by_user(account.user_id)

        assert len(accounts) == 2

        account_ids = {acc.id for acc in accounts}

        assert account.id in account_ids
        assert new_account.id in account_ids
        assert all(acc.archived_at is None for acc in accounts)

    async def test_get_by_user_default_excludes_archived_accounts(
            self,
            account_repository: AccountRepository,
            account: Account,
            archived_account: Account,
    ):
        accounts = await account_repository.get_by_user(account.user_id)

        assert len(accounts) == 1
        assert accounts[0].id == account.id
        assert accounts[0].archived_at is None

    async def test_get_by_user_returns_empty_list(
            self,
            account_repository: AccountRepository,
            user: User,
    ):
        accounts = await account_repository.get_by_user(user.id)

        assert accounts == []

    async def test_get_by_user_default_returns_only_own_accounts(
            self,
            test_session: AsyncSession,
            account_repository: AccountRepository,
            account: Account,
            uah_currency: Currency,
    ):
        other_user_repository = UserRepository(test_session)
        other_user = await other_user_repository.create(User(
            email="other@test.com",
            username="other",
            hashed_password="hashed",
        ))

        other_account = await account_repository.create(Account(
            name="Other User Account",
            currency_code=uah_currency.code,
            user_id=other_user.id,
        ))

        accounts = await account_repository.get_by_user(account.user_id)

        assert len(accounts) == 1
        assert accounts[0].id == account.id
        assert other_account.id not in {acc.id for acc in accounts}

    async def test_get_by_user_status_archived_returns_only_archived_accounts(
            self,
            account_repository: AccountRepository,
            account: Account,
            archived_account: Account,
    ):
        accounts = await account_repository.get_by_user(
            account.user_id,
            status=AccountStatus.ARCHIVED,
        )

        assert len(accounts) == 1
        assert accounts[0].id == archived_account.id
        assert accounts[0].archived_at is not None

    async def test_get_by_user_status_all_returns_active_and_archived_accounts(
            self,
            account_repository: AccountRepository,
            account: Account,
            archived_account: Account,
    ):
        accounts = await account_repository.get_by_user(
            account.user_id,
            status=AccountStatus.ALL,
        )

        assert len(accounts) == 2

        account_ids = {acc.id for acc in accounts}

        assert account.id in account_ids
        assert archived_account.id in account_ids

    async def test_get_by_user_status_all_returns_only_own_accounts(
            self,
            test_session: AsyncSession,
            account_repository: AccountRepository,
            account: Account,
            archived_account: Account,
            uah_currency: Currency,
    ):
        other_user_repository = UserRepository(test_session)
        other_user = await other_user_repository.create(User(
            email="other@test.com",
            username="other",
            hashed_password="hashed",
        ))

        other_active_account = await account_repository.create(Account(
            name="Other Active Account",
            currency_code=uah_currency.code,
            user_id=other_user.id,
        ))

        other_archived_account = await account_repository.create(Account(
            name="Other Archived Account",
            currency_code=uah_currency.code,
            user_id=other_user.id,
            archived_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        ))

        accounts = await account_repository.get_by_user(
            account.user_id,
            status=AccountStatus.ALL,
        )

        assert len(accounts) == 2

        account_ids = {acc.id for acc in accounts}

        assert account.id in account_ids
        assert archived_account.id in account_ids
        assert other_active_account.id not in account_ids
        assert other_archived_account.id not in account_ids


class TestGetByUserAndName:
    async def test_get_by_user_and_name(
            self,
            account_repository: AccountRepository,
            account: Account,
    ):
        found_account = await account_repository.get_by_user_and_name(account.user_id, account.name)

        assert found_account.id == account.id
        assert found_account.name == account.name
        assert found_account.user_id == account.user_id

    async def test_get_by_user_and_name_finds_archived(
            self,
            account_repository: AccountRepository,
            user: User,
            archived_account: Account,
    ):
        found_account = await account_repository.get_by_user_and_name(user.id, archived_account.name)

        assert found_account.id == archived_account.id
        assert found_account.archived_at is not None

    async def test_get_by_user_and_name_not_found(
            self,
            account_repository: AccountRepository,
            user: User,
    ):
        found_account = await account_repository.get_by_user_and_name(user.id, "wrong name")

        assert found_account is None


class TestArchive:
    async def test_archive(
            self,
            account_repository: AccountRepository,
            account: Account,
    ):
        await account_repository.archive(account)

        archived = await account_repository.get_by_id(account.id)

        assert archived.id == account.id
        assert archived.name == account.name
        assert archived.archived_at is not None


class TestRestore:
    async def test_restore(
            self,
            account_repository: AccountRepository,
            archived_account: Account,
    ):
        await account_repository.restore(archived_account)

        restored = await account_repository.get_by_id(archived_account.id)

        assert restored.id == archived_account.id
        assert restored.name == archived_account.name
        assert restored.archived_at is None


class TestUpdate:
    async def test_update(
            self,
            account_repository: AccountRepository,
            account: Account,
    ):
        account.name = "Renamed Account"

        updated_account = await account_repository.update(account)

        assert updated_account.id == account.id
        assert updated_account.name == account.name

        found_account = await account_repository.get_by_id(account.id)
        assert found_account.name == account.name

    async def test_update_does_not_change_currency(
            self,
            account_repository: AccountRepository,
            account: Account,
    ):
        original_currency = account.currency_code

        account.name = "Renamed Account"
        await account_repository.update(account)

        found_account = await account_repository.get_by_id(account.id)

        assert found_account.currency_code == original_currency