from datetime import date
from decimal import Decimal

import pytest

from app.models import (
    Account,
    Category,
    Currency,
    Transaction,
    TransactionKind,
    TransactionSplit,
    TransactionType,
    User,
)
from app.repositories import (
    AccountRepository,
    TransactionRepository,
    TransactionSplitRepository,
    UserRepository,
)
from tests.integration.repositories.helpers import make_transaction


@pytest.fixture
async def split_transaction(
    transaction_repository: TransactionRepository,
    user: User,
    uah_account: Account,
    uah_currency: Currency,
):
    """A 1000 UAH receipt with no category of its own: it is meant to be split."""
    return await transaction_repository.add(
        make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            description="ATB",
            amount=Decimal("1000.00"),
            currency_code=uah_currency.code,
            category_id=None,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2026, 2, 10),
        )
    )


@pytest.fixture
async def other_transaction(
    transaction_repository: TransactionRepository,
    user: User,
    uah_account: Account,
    uah_currency: Currency,
):
    """A second split transaction, to prove queries do not leak across transactions."""
    return await transaction_repository.add(
        make_transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.REGULAR,
            description="Silpo",
            amount=Decimal("500.00"),
            currency_code=uah_currency.code,
            category_id=None,
            user_id=user.id,
            account_id=uah_account.id,
            date=date(2026, 2, 11),
        )
    )


@pytest.fixture
async def splits(
    transaction_split_repository: TransactionSplitRepository,
    split_transaction: Transaction,
    category: Category,
):
    return await transaction_split_repository.add_all(
        [
            TransactionSplit(
                transaction_id=split_transaction.id,
                category_id=category.id,
                amount=Decimal("800.00"),
                settled_amount=Decimal("800.00"),
                description="Groceries",
            ),
            TransactionSplit(
                transaction_id=split_transaction.id,
                category_id=None,
                amount=Decimal("200.00"),
                settled_amount=Decimal("200.00"),
                description="Household",
            ),
        ]
    )


class TestAddAll:
    async def test_add_all(
        self,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
        category: Category,
    ):
        created_splits = await transaction_split_repository.add_all(
            [
                TransactionSplit(
                    transaction_id=split_transaction.id,
                    category_id=category.id,
                    amount=Decimal("800.00"),
                    settled_amount=Decimal("800.00"),
                    description="Groceries",
                ),
                TransactionSplit(
                    transaction_id=split_transaction.id,
                    category_id=None,
                    amount=Decimal("200.00"),
                    settled_amount=Decimal("200.00"),
                ),
            ]
        )

        assert len(created_splits) == 2

        assert created_splits[0].id is not None
        assert created_splits[1].id is not None
        assert created_splits[0].id != created_splits[1].id

        assert created_splits[0].transaction_id == split_transaction.id
        assert created_splits[0].category_id == category.id
        assert created_splits[0].amount == Decimal("800.00")
        assert created_splits[0].settled_amount == Decimal("800.00")
        assert created_splits[0].description == "Groceries"
        assert created_splits[0].created_at is not None
        assert created_splits[0].updated_at is not None

        assert created_splits[1].category_id is None
        assert created_splits[1].description is None

    async def test_add_all_keeps_cross_currency_amounts_apart(
        self,
        transaction_repository: TransactionRepository,
        transaction_split_repository: TransactionSplitRepository,
        user: User,
        uah_account: Account,
        category: Category,
        uah_currency: Currency,
        usd_currency: Currency,
    ):
        """A USD receipt charged in UAH: the split keeps both the receipt and the settled amount."""
        transaction = await transaction_repository.add(
            make_transaction(
                type=TransactionType.EXPENSE,
                kind=TransactionKind.REGULAR,
                description="Lidl",
                amount=Decimal("24.00"),
                currency_code=usd_currency.code,
                settled_amount=Decimal("1000.00"),
                settled_currency_code=uah_currency.code,
                category_id=None,
                user_id=user.id,
                account_id=uah_account.id,
                date=date(2026, 2, 10),
            )
        )

        await transaction_split_repository.add_all(
            [
                TransactionSplit(
                    transaction_id=transaction.id,
                    category_id=category.id,
                    amount=Decimal("2.00"),
                    settled_amount=Decimal("83.33"),
                ),
                TransactionSplit(
                    transaction_id=transaction.id,
                    category_id=None,
                    amount=Decimal("22.00"),
                    settled_amount=Decimal("916.67"),
                ),
            ]
        )

        found_splits = await transaction_split_repository.get_by_transaction(transaction.id)

        assert sum(split.amount for split in found_splits) == Decimal("24.00")
        assert sum(split.settled_amount for split in found_splits) == Decimal("1000.00")


class TestGetByTransaction:
    async def test_get_by_transaction(
        self,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
        splits,
        category: Category,
    ):
        found_splits = await transaction_split_repository.get_by_transaction(split_transaction.id)

        assert len(found_splits) == 2

        assert all(split.transaction_id == split_transaction.id for split in found_splits)

        assert found_splits[0].amount == Decimal("800.00")
        assert found_splits[0].category_id == category.id
        assert found_splits[1].amount == Decimal("200.00")
        assert found_splits[1].category_id is None

    async def test_get_by_transaction_ordered_by_id(
        self,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
        splits,
    ):
        found_splits = await transaction_split_repository.get_by_transaction(split_transaction.id)

        assert [split.id for split in found_splits] == sorted(split.id for split in found_splits)

    async def test_get_by_transaction_empty(
        self,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
    ):
        found_splits = await transaction_split_repository.get_by_transaction(split_transaction.id)

        assert found_splits == []

    async def test_get_by_transaction_returns_only_own(
        self,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
        other_transaction: Transaction,
        splits,
        category: Category,
    ):
        await transaction_split_repository.add_all(
            [
                TransactionSplit(
                    transaction_id=other_transaction.id,
                    category_id=category.id,
                    amount=Decimal("300.00"),
                    settled_amount=Decimal("300.00"),
                ),
                TransactionSplit(
                    transaction_id=other_transaction.id,
                    category_id=None,
                    amount=Decimal("200.00"),
                    settled_amount=Decimal("200.00"),
                ),
            ]
        )

        found_splits = await transaction_split_repository.get_by_transaction(split_transaction.id)

        assert len(found_splits) == 2
        assert all(split.transaction_id == split_transaction.id for split in found_splits)


class TestDeleteByTransaction:
    async def test_delete_by_transaction(
        self,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
        splits,
    ):
        await transaction_split_repository.delete_by_transaction(split_transaction.id)

        found_splits = await transaction_split_repository.get_by_transaction(split_transaction.id)

        assert found_splits == []

    async def test_delete_by_transaction_keeps_other_transactions(
        self,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
        other_transaction: Transaction,
        splits,
        category: Category,
    ):
        await transaction_split_repository.add_all(
            [
                TransactionSplit(
                    transaction_id=other_transaction.id,
                    category_id=category.id,
                    amount=Decimal("300.00"),
                    settled_amount=Decimal("300.00"),
                ),
                TransactionSplit(
                    transaction_id=other_transaction.id,
                    category_id=None,
                    amount=Decimal("200.00"),
                    settled_amount=Decimal("200.00"),
                ),
            ]
        )

        await transaction_split_repository.delete_by_transaction(split_transaction.id)

        assert await transaction_split_repository.get_by_transaction(split_transaction.id) == []
        assert len(await transaction_split_repository.get_by_transaction(other_transaction.id)) == 2

    async def test_delete_by_transaction_without_splits(
        self,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
    ):
        await transaction_split_repository.delete_by_transaction(split_transaction.id)

        assert await transaction_split_repository.get_by_transaction(split_transaction.id) == []


class TestGetTransactionIdsWithSplits:
    async def test_get_transaction_ids_with_splits(
        self,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
        other_transaction: Transaction,
        splits,
    ):
        ids_with_splits = await transaction_split_repository.get_transaction_ids_with_splits(
            [split_transaction.id, other_transaction.id]
        )

        assert ids_with_splits == {split_transaction.id}

    async def test_get_transaction_ids_with_splits_deduplicates(
        self,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
        splits,
    ):
        """Two splits belong to one transaction: the id is reported once."""
        ids_with_splits = await transaction_split_repository.get_transaction_ids_with_splits(
            [split_transaction.id]
        )

        assert ids_with_splits == {split_transaction.id}

    async def test_get_transaction_ids_with_splits_empty(
        self,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
    ):
        ids_with_splits = await transaction_split_repository.get_transaction_ids_with_splits(
            [split_transaction.id]
        )

        assert ids_with_splits == set()

    async def test_get_transaction_ids_with_splits_ignores_unrequested(
        self,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
        other_transaction: Transaction,
        splits,
        category: Category,
    ):
        await transaction_split_repository.add_all(
            [
                TransactionSplit(
                    transaction_id=other_transaction.id,
                    category_id=category.id,
                    amount=Decimal("300.00"),
                    settled_amount=Decimal("300.00"),
                ),
                TransactionSplit(
                    transaction_id=other_transaction.id,
                    category_id=None,
                    amount=Decimal("200.00"),
                    settled_amount=Decimal("200.00"),
                ),
            ]
        )

        ids_with_splits = await transaction_split_repository.get_transaction_ids_with_splits(
            [other_transaction.id]
        )

        assert ids_with_splits == {other_transaction.id}


class TestCascade:
    async def test_deleting_transaction_removes_its_splits(
        self,
        transaction_repository: TransactionRepository,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
        splits,
    ):
        """ON DELETE CASCADE: a split cannot outlive the transaction it explains."""
        transaction_id = split_transaction.id

        await transaction_repository.delete(split_transaction)

        assert await transaction_repository.get_by_id(transaction_id) is None
        assert await transaction_split_repository.get_by_transaction(transaction_id) == []

    async def test_deleting_transaction_keeps_other_splits(
        self,
        transaction_repository: TransactionRepository,
        transaction_split_repository: TransactionSplitRepository,
        split_transaction: Transaction,
        other_transaction: Transaction,
        splits,
        category: Category,
    ):
        await transaction_split_repository.add_all(
            [
                TransactionSplit(
                    transaction_id=other_transaction.id,
                    category_id=category.id,
                    amount=Decimal("300.00"),
                    settled_amount=Decimal("300.00"),
                ),
                TransactionSplit(
                    transaction_id=other_transaction.id,
                    category_id=None,
                    amount=Decimal("200.00"),
                    settled_amount=Decimal("200.00"),
                ),
            ]
        )

        await transaction_repository.delete(split_transaction)

        assert len(await transaction_split_repository.get_by_transaction(other_transaction.id)) == 2


class TestOwnership:
    async def test_splits_of_another_user_are_reachable_only_through_their_transaction(
        self,
        account_repository: AccountRepository,
        transaction_repository: TransactionRepository,
        transaction_split_repository: TransactionSplitRepository,
        user_repository: UserRepository,
        split_transaction: Transaction,
        splits,
        uah_currency: Currency,
    ):
        """Splits carry no user_id: ownership is checked on the parent transaction."""
        other_user = await user_repository.add(
            User(
                email="othersplit@test.com",
                username="othersplit",
                hashed_password="hashed_password",
            )
        )

        other_account = await account_repository.add(
            Account(
                name="Other user account",
                currency_code=uah_currency.code,
                user_id=other_user.id,
            )
        )

        other_user_transaction = await transaction_repository.add(
            make_transaction(
                type=TransactionType.EXPENSE,
                kind=TransactionKind.REGULAR,
                amount=Decimal("400.00"),
                description="Other user receipt",
                currency_code=uah_currency.code,
                category_id=None,
                user_id=other_user.id,
                account_id=other_account.id,
                date=date(2026, 2, 12),
            )
        )

        await transaction_split_repository.add_all(
            [
                TransactionSplit(
                    transaction_id=other_user_transaction.id,
                    category_id=None,
                    amount=Decimal("250.00"),
                    settled_amount=Decimal("250.00"),
                ),
                TransactionSplit(
                    transaction_id=other_user_transaction.id,
                    category_id=None,
                    amount=Decimal("150.00"),
                    settled_amount=Decimal("150.00"),
                ),
            ]
        )

        found_splits = await transaction_split_repository.get_by_transaction(split_transaction.id)

        assert len(found_splits) == 2
        assert all(split.transaction_id == split_transaction.id for split in found_splits)
