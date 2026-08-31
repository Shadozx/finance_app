from decimal import Decimal

import pytest

from app.models import (
    Category,
    Currency,
    TransactionTemplate,
    TransactionTemplateSplit,
    TransactionType,
    User,
)
from app.repositories import (
    TransactionTemplateRepository,
    TransactionTemplateSplitRepository,
    UserRepository,
)


@pytest.fixture
async def split_template(
    transaction_template_repository: TransactionTemplateRepository,
    user: User,
    uah_currency: Currency,
):
    """A 1000 UAH template with no category of its own: it is meant to be split."""
    return await transaction_template_repository.add(
        TransactionTemplate(
            name="ATB",
            type=TransactionType.EXPENSE,
            description="Weekly groceries",
            amount=Decimal("1000.00"),
            currency_code=uah_currency.code,
            category_id=None,
            user_id=user.id,
        )
    )


@pytest.fixture
async def other_template(
    transaction_template_repository: TransactionTemplateRepository,
    user: User,
    uah_currency: Currency,
):
    """A second split template, to prove queries do not leak across templates."""
    return await transaction_template_repository.add(
        TransactionTemplate(
            name="Silpo",
            type=TransactionType.EXPENSE,
            description="Groceries on the way home",
            amount=Decimal("500.00"),
            currency_code=uah_currency.code,
            category_id=None,
            user_id=user.id,
        )
    )


@pytest.fixture
async def splits(
    transaction_template_split_repository: TransactionTemplateSplitRepository,
    split_template: TransactionTemplate,
    category: Category,
):
    return await transaction_template_split_repository.add_all(
        [
            TransactionTemplateSplit(
                transaction_template_id=split_template.id,
                category_id=category.id,
                amount=Decimal("800.00"),
                description="Groceries",
            ),
            TransactionTemplateSplit(
                transaction_template_id=split_template.id,
                category_id=None,
                amount=Decimal("200.00"),
                description="Household",
            ),
        ]
    )


class TestAddAll:
    async def test_add_all(
        self,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
        category: Category,
    ):
        created_splits = await transaction_template_split_repository.add_all(
            [
                TransactionTemplateSplit(
                    transaction_template_id=split_template.id,
                    category_id=category.id,
                    amount=Decimal("800.00"),
                    description="Groceries",
                ),
                TransactionTemplateSplit(
                    transaction_template_id=split_template.id,
                    category_id=None,
                    amount=Decimal("200.00"),
                ),
            ]
        )

        assert len(created_splits) == 2

        assert created_splits[0].id is not None
        assert created_splits[1].id is not None
        assert created_splits[0].id != created_splits[1].id

        assert created_splits[0].transaction_template_id == split_template.id
        assert created_splits[0].category_id == category.id
        assert created_splits[0].amount == Decimal("800.00")
        assert created_splits[0].description == "Groceries"
        assert created_splits[0].created_at is not None
        assert created_splits[0].updated_at is not None

        assert created_splits[1].category_id is None
        assert created_splits[1].description is None


class TestGetByTemplate:
    async def test_get_by_template(
        self,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
        splits,
        category: Category,
    ):
        found_splits = await transaction_template_split_repository.get_by_template(
            split_template.id
        )

        assert len(found_splits) == 2

        assert all(split.transaction_template_id == split_template.id for split in found_splits)

        assert found_splits[0].amount == Decimal("800.00")
        assert found_splits[0].category_id == category.id
        assert found_splits[1].amount == Decimal("200.00")
        assert found_splits[1].category_id is None

    async def test_get_by_template_ordered_by_id(
        self,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
        splits,
    ):
        found_splits = await transaction_template_split_repository.get_by_template(
            split_template.id
        )

        assert [split.id for split in found_splits] == sorted(split.id for split in found_splits)

    async def test_get_by_template_empty(
        self,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
    ):
        found_splits = await transaction_template_split_repository.get_by_template(
            split_template.id
        )

        assert found_splits == []

    async def test_get_by_template_returns_only_own(
        self,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
        other_template: TransactionTemplate,
        splits,
        category: Category,
    ):
        await transaction_template_split_repository.add_all(
            [
                TransactionTemplateSplit(
                    transaction_template_id=other_template.id,
                    category_id=category.id,
                    amount=Decimal("300.00"),
                ),
                TransactionTemplateSplit(
                    transaction_template_id=other_template.id,
                    category_id=None,
                    amount=Decimal("200.00"),
                ),
            ]
        )

        found_splits = await transaction_template_split_repository.get_by_template(
            split_template.id
        )

        assert len(found_splits) == 2
        assert all(split.transaction_template_id == split_template.id for split in found_splits)


class TestDeleteByTemplate:
    async def test_delete_by_template(
        self,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
        splits,
    ):
        await transaction_template_split_repository.delete_by_template(split_template.id)

        found_splits = await transaction_template_split_repository.get_by_template(
            split_template.id
        )

        assert found_splits == []

    async def test_delete_by_template_keeps_other_templates(
        self,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
        other_template: TransactionTemplate,
        splits,
        category: Category,
    ):
        await transaction_template_split_repository.add_all(
            [
                TransactionTemplateSplit(
                    transaction_template_id=other_template.id,
                    category_id=category.id,
                    amount=Decimal("300.00"),
                ),
                TransactionTemplateSplit(
                    transaction_template_id=other_template.id,
                    category_id=None,
                    amount=Decimal("200.00"),
                ),
            ]
        )

        await transaction_template_split_repository.delete_by_template(split_template.id)

        assert await transaction_template_split_repository.get_by_template(split_template.id) == []
        assert (
            len(await transaction_template_split_repository.get_by_template(other_template.id)) == 2
        )

    async def test_delete_by_template_without_splits(
        self,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
    ):
        await transaction_template_split_repository.delete_by_template(split_template.id)

        assert await transaction_template_split_repository.get_by_template(split_template.id) == []


class TestGetTemplateIdsWithSplits:
    async def test_get_template_ids_with_splits(
        self,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
        other_template: TransactionTemplate,
        splits,
    ):
        ids_with_splits = await transaction_template_split_repository.get_template_ids_with_splits(
            [split_template.id, other_template.id]
        )

        assert ids_with_splits == {split_template.id}

    async def test_get_template_ids_with_splits_deduplicates(
        self,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
        splits,
    ):
        """Two splits belong to one template: the id is reported once."""
        ids_with_splits = await transaction_template_split_repository.get_template_ids_with_splits(
            [split_template.id]
        )

        assert ids_with_splits == {split_template.id}

    async def test_get_template_ids_with_splits_empty(
        self,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
    ):
        ids_with_splits = await transaction_template_split_repository.get_template_ids_with_splits(
            [split_template.id]
        )

        assert ids_with_splits == set()

    async def test_get_template_ids_with_splits_ignores_unrequested(
        self,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
        other_template: TransactionTemplate,
        splits,
        category: Category,
    ):
        await transaction_template_split_repository.add_all(
            [
                TransactionTemplateSplit(
                    transaction_template_id=other_template.id,
                    category_id=category.id,
                    amount=Decimal("300.00"),
                ),
                TransactionTemplateSplit(
                    transaction_template_id=other_template.id,
                    category_id=None,
                    amount=Decimal("200.00"),
                ),
            ]
        )

        ids_with_splits = await transaction_template_split_repository.get_template_ids_with_splits(
            [other_template.id]
        )

        assert ids_with_splits == {other_template.id}


class TestCascade:
    async def test_deleting_template_removes_its_splits(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
        splits,
    ):
        """ON DELETE CASCADE: a split cannot outlive the template it belongs to."""
        template_id = split_template.id

        await transaction_template_repository.delete(split_template)

        assert await transaction_template_repository.get_by_id(template_id) is None
        assert await transaction_template_split_repository.get_by_template(template_id) == []

    async def test_deleting_template_keeps_other_splits(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        split_template: TransactionTemplate,
        other_template: TransactionTemplate,
        splits,
        category: Category,
    ):
        await transaction_template_split_repository.add_all(
            [
                TransactionTemplateSplit(
                    transaction_template_id=other_template.id,
                    category_id=category.id,
                    amount=Decimal("300.00"),
                ),
                TransactionTemplateSplit(
                    transaction_template_id=other_template.id,
                    category_id=None,
                    amount=Decimal("200.00"),
                ),
            ]
        )

        await transaction_template_repository.delete(split_template)

        assert (
            len(await transaction_template_split_repository.get_by_template(other_template.id)) == 2
        )


class TestOwnership:
    async def test_splits_of_another_user_are_reachable_only_through_their_template(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        transaction_template_split_repository: TransactionTemplateSplitRepository,
        user_repository: UserRepository,
        split_template: TransactionTemplate,
        splits,
        uah_currency: Currency,
    ):
        """Splits carry no user_id: ownership is checked on the parent template."""
        other_user = await user_repository.add(
            User(
                email="othertemplatesplit@test.com",
                username="othertemplatesplit",
                hashed_password="hashed_password",
            )
        )

        other_user_template = await transaction_template_repository.add(
            TransactionTemplate(
                name="Other user template",
                type=TransactionType.EXPENSE,
                description="Other user groceries",
                amount=Decimal("400.00"),
                currency_code=uah_currency.code,
                category_id=None,
                user_id=other_user.id,
            )
        )

        await transaction_template_split_repository.add_all(
            [
                TransactionTemplateSplit(
                    transaction_template_id=other_user_template.id,
                    category_id=None,
                    amount=Decimal("250.00"),
                ),
                TransactionTemplateSplit(
                    transaction_template_id=other_user_template.id,
                    category_id=None,
                    amount=Decimal("150.00"),
                ),
            ]
        )

        found_splits = await transaction_template_split_repository.get_by_template(
            split_template.id
        )

        assert len(found_splits) == 2
        assert all(split.transaction_template_id == split_template.id for split in found_splits)
