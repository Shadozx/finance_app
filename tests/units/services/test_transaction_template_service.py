from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pytest_mock import MockerFixture

from app.core import UnitOfWork
from app.core.exceptions import NotAllowedActionException, NotFoundException, ValueExistsException
from app.models import Category, Currency, TransactionTemplate, TransactionType
from app.repositories import (
    CategoryRepository,
    CurrencyRepository,
    TransactionTemplateRepository,
    TransactionTemplateSplitRepository,
)
from app.schemas import (
    TransactionTemplateCreate,
    TransactionTemplateListItem,
    TransactionTemplateResponse,
    TransactionTemplateSplitCreate,
    TransactionTemplateSplitResponse,
    TransactionTemplateUpdate,
)
from app.services import TransactionTemplateService, validators
from tests.units.services.helpers import (
    as_persisted,
    as_persisted_all,
    assert_model_fields,
    make_transaction_template,
    make_transaction_template_split,
)


class TestCreateTemplate:
    @pytest.fixture
    def data(
        self,
        existing_template: TransactionTemplate,
        existing_currency: Currency,
    ):
        return TransactionTemplateCreate(
            type=TransactionType.EXPENSE,
            name=existing_template.name,
            amount=existing_template.amount,
            description=existing_template.description,
            currency_code=existing_currency.code,
        )

    async def test_create_template_success(
        self,
        mocker: MockerFixture,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionTemplateCreate,
    ):
        data.category_id = existing_category.id
        user_id = existing_category.user_id

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = existing_category

        transaction_template_repo_mock.add.side_effect = as_persisted

        validate_category_spy = mocker.spy(validators, "validate_category")
        validate_currency_spy = mocker.spy(validators, "validate_currency")

        result = await transaction_template_service.create_template(data, user_id=user_id)

        call_args = transaction_template_repo_mock.add.call_args[0][0]

        assert result == TransactionTemplateResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            name=data.name,
            user_id=user_id,
            type=TransactionType.EXPENSE,
            amount=data.amount,
        )

        validate_category_spy.assert_called_once_with(
            transaction_template_service.category_repository, user_id, existing_category.id
        )
        validate_currency_spy.assert_called_once_with(
            transaction_template_service.currency_repository, existing_currency.code
        )

        transaction_template_repo_mock.get_by_user_and_name.assert_called_once_with(
            data.name, user_id
        )

        transaction_template_repo_mock.add.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_create_template_without_category(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_currency: Currency,
        data: TransactionTemplateCreate,
    ):
        user_id = 1

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = None

        transaction_template_repo_mock.add.side_effect = as_persisted

        result = await transaction_template_service.create_template(data, user_id)

        call_args = transaction_template_repo_mock.add.call_args[0][0]

        assert result == TransactionTemplateResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            name=data.name,
            user_id=user_id,
            type=TransactionType.EXPENSE,
            amount=data.amount,
        )

        transaction_template_repo_mock.get_by_user_and_name.assert_called_once_with(
            data.name, user_id
        )

        transaction_template_repo_mock.add.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_create_template_duplicate_name(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        unit_of_work_mock: UnitOfWork,
        existing_template: TransactionTemplate,
        data: TransactionTemplateCreate,
    ):
        user_id = existing_template.user_id

        transaction_template_repo_mock.get_by_user_and_name.return_value = existing_template

        with pytest.raises(
            ValueExistsException, match="Transaction template with this name already exists"
        ):
            await transaction_template_service.create_template(data, user_id)

        transaction_template_repo_mock.get_by_user_and_name.assert_called_once_with(
            data.name, user_id
        )

        transaction_template_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_template_archived_category(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_category: Category,
        data: TransactionTemplateCreate,
    ):
        data.category_id = existing_category.id
        user_id = existing_category.user_id
        existing_category.archived_at = datetime.now(UTC)

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        category_repo_mock.get_by_id.return_value = existing_category

        with pytest.raises(
            NotAllowedActionException, match="Archived category is not allowed to use"
        ):
            await transaction_template_service.create_template(data, user_id)

        transaction_template_repo_mock.get_by_user_and_name.assert_called_once_with(
            data.name, user_id
        )

        transaction_template_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_template_with_splits(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionTemplateCreate,
    ):
        user_id = existing_category.user_id

        data.category_id = None
        data.splits = [
            TransactionTemplateSplitCreate(
                category_id=existing_category.id,
                amount=Decimal("30.00"),
                description="Coffee",
            ),
            TransactionTemplateSplitCreate(
                category_id=existing_category.id + 1,
                amount=Decimal("20.00"),
            ),
        ]

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = existing_category

        transaction_template_repo_mock.add.side_effect = as_persisted
        transaction_template_split_repo_mock.add_all.side_effect = as_persisted_all

        result = await transaction_template_service.create_template(data, user_id)

        created_template = transaction_template_repo_mock.add.call_args[0][0]

        assert created_template.category_id is None

        splits = transaction_template_split_repo_mock.add_all.call_args[0][0]

        assert len(splits) == 2

        assert_model_fields(
            splits[0],
            transaction_template_id=created_template.id,
            category_id=existing_category.id,
            amount=Decimal("30.00"),
            description="Coffee",
        )

        assert_model_fields(
            splits[1],
            transaction_template_id=created_template.id,
            category_id=existing_category.id + 1,
            amount=Decimal("20.00"),
        )

        assert result.has_splits is True
        assert len(result.splits) == 2

        transaction_template_split_repo_mock.add_all.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_create_template_validates_split_categories(
        self,
        mocker: MockerFixture,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionTemplateCreate,
    ):
        """Three parts share two categories: each distinct one is validated once."""
        user_id = existing_category.user_id

        data.category_id = None
        data.splits = [
            TransactionTemplateSplitCreate(
                category_id=existing_category.id, amount=Decimal("20.00")
            ),
            TransactionTemplateSplitCreate(
                category_id=existing_category.id + 1, amount=Decimal("20.00")
            ),
            TransactionTemplateSplitCreate(
                category_id=existing_category.id, amount=Decimal("10.00")
            ),
        ]

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = existing_category

        transaction_template_repo_mock.add.side_effect = as_persisted
        transaction_template_split_repo_mock.add_all.side_effect = as_persisted_all

        validate_category_spy = mocker.spy(validators, "validate_category")

        await transaction_template_service.create_template(data, user_id)

        # One call for the template's own (None) category, two for the deduplicated splits.
        assert validate_category_spy.call_count == 3

        assert category_repo_mock.get_by_id.call_count == 2

        assert {call.args[0] for call in category_repo_mock.get_by_id.call_args_list} == {
            existing_category.id,
            existing_category.id + 1,
        }

        splits = transaction_template_split_repo_mock.add_all.call_args[0][0]

        assert len(splits) == 3

    async def test_create_template_split_category_not_found(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionTemplateCreate,
    ):
        """Splits are validated before anything is written: the template is never created."""
        user_id = existing_category.user_id

        missing_category_id = existing_category.id + 1

        data.category_id = None
        data.splits = [
            TransactionTemplateSplitCreate(
                category_id=existing_category.id, amount=Decimal("30.00")
            ),
            TransactionTemplateSplitCreate(
                category_id=missing_category_id, amount=Decimal("20.00")
            ),
        ]

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.side_effect = lambda category_id: (
            existing_category if category_id == existing_category.id else None
        )

        with pytest.raises(NotFoundException, match="Category not found"):
            await transaction_template_service.create_template(data, user_id)

        transaction_template_repo_mock.add.assert_not_called()

        transaction_template_split_repo_mock.add_all.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_template_inactive_currency(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_currency: Currency,
        data: TransactionTemplateCreate,
    ):
        user_id = 1

        transaction_template_repo_mock.get_by_user_and_name.return_value = None

        existing_currency.is_active = False
        currency_repo_mock.get_by_code.return_value = existing_currency

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await transaction_template_service.create_template(data, user_id)

        transaction_template_repo_mock.get_by_user_and_name.assert_called_once_with(
            data.name, user_id
        )

        transaction_template_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()


class TestUpdateTemplate:
    @pytest.fixture
    def data(
        self,
        existing_template: TransactionTemplate,
    ):
        return TransactionTemplateUpdate(
            type=existing_template.type,
            amount=Decimal("100.00"),
            name="Early Morning Coffee",
            currency_code=existing_template.currency_code,
            description=existing_template.description,
        )

    async def test_update_template_success(
        self,
        mocker: MockerFixture,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_template: TransactionTemplate,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionTemplateUpdate,
    ):
        user_id = existing_template.user_id
        data.category_id = existing_category.id

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        transaction_template_repo_mock.get_by_id.return_value = existing_template
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        transaction_template_split_repo_mock.get_by_template.return_value = []

        transaction_template_repo_mock.update.side_effect = as_persisted

        validate_template_spy = mocker.spy(validators, "validate_template")
        validate_category_spy = mocker.spy(validators, "validate_category")
        validate_currency_spy = mocker.spy(validators, "validate_currency")

        result = await transaction_template_service.update_template(
            existing_template.id, data, user_id
        )

        call_args = transaction_template_repo_mock.update.call_args[0][0]

        assert result == TransactionTemplateResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            name=data.name,
            user_id=existing_template.user_id,
            type=data.type,
            amount=data.amount,
        )

        validate_template_spy.assert_called_once_with(
            transaction_template_service.transaction_template_repository,
            user_id,
            existing_template.id,
        )

        validate_category_spy.assert_called_once_with(
            transaction_template_service.category_repository,
            user_id,
            existing_category.id,
            allow_archived=False,
        )
        validate_currency_spy.assert_called_once_with(
            transaction_template_service.currency_repository,
            existing_currency.code,
            allow_inactive=True,
        )

        transaction_template_repo_mock.get_by_user_and_name.assert_called_once_with(
            data.name, user_id
        )

        transaction_template_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_template_without_category(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
        category_repo_mock: CategoryRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_template: TransactionTemplate,
        existing_currency: Currency,
        data: TransactionTemplateUpdate,
    ):
        data.category_id = None
        user_id = existing_template.user_id

        transaction_template_repo_mock.get_by_user_and_name.return_value = existing_template
        transaction_template_repo_mock.get_by_id.return_value = existing_template
        currency_repo_mock.get_by_code.return_value = existing_currency
        transaction_template_split_repo_mock.get_by_template.return_value = []

        transaction_template_repo_mock.update.side_effect = as_persisted

        result = await transaction_template_service.update_template(
            existing_template.id, data, user_id
        )

        call_args = transaction_template_repo_mock.update.call_args[0][0]

        assert result == TransactionTemplateResponse.model_validate(call_args)

        transaction_template_repo_mock.get_by_user_and_name.assert_called_once_with(
            data.name, user_id
        )

        transaction_template_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_template_duplicate_name(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        unit_of_work_mock: UnitOfWork,
        existing_template: TransactionTemplate,
        data: TransactionTemplateUpdate,
    ):
        user_id = existing_template.user_id
        duplicate = make_transaction_template(
            id=999,
            name=data.name,
            user_id=user_id,
        )

        transaction_template_repo_mock.get_by_user_and_name.return_value = duplicate

        with pytest.raises(
            ValueExistsException, match="Transaction template with this name already exists"
        ):
            await transaction_template_service.update_template(existing_template.id, data, user_id)

        transaction_template_repo_mock.get_by_user_and_name.assert_called_once_with(
            data.name, user_id
        )

        transaction_template_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_template_self_not_duplicate(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
        category_repo_mock: CategoryRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_template: TransactionTemplate,
        existing_currency: Currency,
        data: TransactionTemplateUpdate,
    ):
        data.name = existing_template.name
        user_id = existing_template.user_id

        transaction_template_repo_mock.get_by_user_and_name.return_value = existing_template
        transaction_template_repo_mock.get_by_id.return_value = existing_template
        currency_repo_mock.get_by_code.return_value = existing_currency
        transaction_template_split_repo_mock.get_by_template.return_value = []

        updated = existing_template
        transaction_template_repo_mock.update.return_value = updated

        result = await transaction_template_service.update_template(
            existing_template.id, data, user_id
        )

        assert result == TransactionTemplateResponse.model_validate(updated)

        transaction_template_repo_mock.get_by_user_and_name.assert_called_once_with(
            data.name, user_id
        )

        transaction_template_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_template_not_found_template(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        unit_of_work_mock: UnitOfWork,
        data: TransactionTemplateUpdate,
    ):
        template_id = 999
        user_id = 1

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        transaction_template_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Transaction template not found"):
            await transaction_template_service.update_template(template_id, data, user_id)

        transaction_template_repo_mock.get_by_user_and_name.assert_called_once_with(
            data.name, user_id
        )

        transaction_template_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_template_inactive_currency(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_template: TransactionTemplate,
        existing_currency: Currency,
        data: TransactionTemplateUpdate,
    ):
        existing_template.category_id = None
        user_id = existing_template.user_id

        data.currency_code = "USD"
        existing_currency.code = "USD"
        existing_currency.is_active = False

        transaction_template_repo_mock.get_by_id.return_value = existing_template
        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        currency_repo_mock.get_by_code.return_value = existing_currency

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await transaction_template_service.update_template(existing_template.id, data, user_id)

        transaction_template_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_template_rejects_archived_category(
        self,
        mocker: MockerFixture,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_template: TransactionTemplate,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionTemplateUpdate,
    ):
        """Keeping the category the template already has is refused once it is archived.

        A template describes the future: unlike a transaction, it gets no pass
        for a category that was archived after the fact.
        """
        user_id = existing_template.user_id

        existing_template.category_id = existing_category.id
        existing_category.archived_at = datetime.now(UTC)

        data.category_id = existing_template.category_id
        data.currency_code = existing_template.currency_code

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        transaction_template_repo_mock.get_by_id.return_value = existing_template
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency

        validate_category_spy = mocker.spy(validators, "validate_category")

        with pytest.raises(
            NotAllowedActionException, match="Archived category is not allowed to use"
        ):
            await transaction_template_service.update_template(existing_template.id, data, user_id)

        validate_category_spy.assert_called_once_with(
            transaction_template_service.category_repository,
            user_id,
            data.category_id,
            allow_archived=False,
        )

        category_repo_mock.get_by_id.assert_called_once_with(data.category_id)

        transaction_template_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_template_keeps_inactive_currency_allowed(
        self,
        mocker: MockerFixture,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_template: TransactionTemplate,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionTemplateUpdate,
    ):
        user_id = existing_template.user_id

        data.category_id = existing_template.category_id
        data.currency_code = existing_template.currency_code

        existing_currency.is_active = False

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        transaction_template_repo_mock.get_by_id.return_value = existing_template
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        transaction_template_repo_mock.update.return_value = existing_template
        transaction_template_split_repo_mock.get_by_template.return_value = []

        validate_currency_spy = mocker.spy(validators, "validate_currency")

        await transaction_template_service.update_template(existing_template.id, data, user_id)

        validate_currency_spy.assert_called_once_with(
            transaction_template_service.currency_repository,
            data.currency_code,
            allow_inactive=True,
        )

        transaction_template_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_template_replaces_splits(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_template: TransactionTemplate,
        existing_currency: Currency,
        existing_category: Category,
        data: TransactionTemplateUpdate,
    ):
        """The old splits are dropped wholesale, not diffed against the new ones."""
        user_id = existing_template.user_id

        data.category_id = None
        data.splits = [
            TransactionTemplateSplitCreate(
                category_id=existing_category.id, amount=Decimal("50.00")
            ),
            TransactionTemplateSplitCreate(
                category_id=existing_category.id + 1, amount=Decimal("30.00")
            ),
            TransactionTemplateSplitCreate(
                category_id=None, amount=Decimal("20.00"), description="Tip"
            ),
        ]

        old_splits = [
            make_transaction_template_split(
                id=1,
                transaction_template_id=existing_template.id,
                amount=Decimal("40.00"),
            ),
            make_transaction_template_split(
                id=2,
                transaction_template_id=existing_template.id,
                amount=Decimal("10.00"),
            ),
        ]

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        transaction_template_repo_mock.get_by_id.return_value = existing_template
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        transaction_template_split_repo_mock.get_by_template.return_value = old_splits

        transaction_template_repo_mock.update.side_effect = as_persisted
        transaction_template_split_repo_mock.add_all.side_effect = as_persisted_all

        result = await transaction_template_service.update_template(
            existing_template.id, data, user_id
        )

        transaction_template_split_repo_mock.delete_by_template.assert_called_once_with(
            existing_template.id
        )

        new_splits = transaction_template_split_repo_mock.add_all.call_args[0][0]

        assert len(new_splits) == 3

        assert_model_fields(
            new_splits[0],
            transaction_template_id=existing_template.id,
            category_id=existing_category.id,
            amount=Decimal("50.00"),
        )

        assert_model_fields(
            new_splits[2],
            transaction_template_id=existing_template.id,
            category_id=None,
            amount=Decimal("20.00"),
            description="Tip",
        )

        assert result.has_splits is True
        assert len(result.splits) == 3

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_template_removes_splits(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_template: TransactionTemplate,
        existing_currency: Currency,
        data: TransactionTemplateUpdate,
    ):
        """Dropping splits turns the template back into a plain one."""
        user_id = existing_template.user_id

        data.category_id = None
        data.splits = None

        old_splits = [
            make_transaction_template_split(
                id=1,
                transaction_template_id=existing_template.id,
                amount=Decimal("40.00"),
            ),
            make_transaction_template_split(
                id=2,
                transaction_template_id=existing_template.id,
                amount=Decimal("10.00"),
            ),
        ]

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        transaction_template_repo_mock.get_by_id.return_value = existing_template
        currency_repo_mock.get_by_code.return_value = existing_currency
        transaction_template_split_repo_mock.get_by_template.return_value = old_splits

        transaction_template_repo_mock.update.side_effect = as_persisted

        result = await transaction_template_service.update_template(
            existing_template.id, data, user_id
        )

        transaction_template_split_repo_mock.delete_by_template.assert_called_once_with(
            existing_template.id
        )

        transaction_template_split_repo_mock.add_all.assert_not_called()

        assert result.has_splits is False
        assert result.splits is None

        unit_of_work_mock.commit.assert_awaited_once()


class TestDeleteTemplate:
    async def test_delete_template_success(
        self,
        mocker: MockerFixture,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        unit_of_work_mock: UnitOfWork,
        existing_template: TransactionTemplate,
    ):
        user_id = existing_template.user_id

        transaction_template_repo_mock.get_by_id.return_value = existing_template

        validate_template_spy = mocker.spy(validators, "validate_template")

        await transaction_template_service.delete_template(existing_template.id, user_id)

        validate_template_spy.assert_called_once_with(
            transaction_template_service.transaction_template_repository,
            user_id,
            existing_template.id,
        )

        transaction_template_repo_mock.delete.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_delete_template_not_found_template(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        unit_of_work_mock: UnitOfWork,
    ):
        template_id = 999
        user_id = 1

        transaction_template_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Transaction template not found"):
            await transaction_template_service.delete_template(template_id, user_id)

        transaction_template_repo_mock.delete.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()


class TestGetTemplate:
    async def test_get_template_success(
        self,
        mocker: MockerFixture,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
        existing_template: TransactionTemplate,
    ):
        user_id = existing_template.user_id

        transaction_template_repo_mock.get_by_id.return_value = existing_template
        transaction_template_split_repo_mock.get_by_template.return_value = []

        validate_template_spy = mocker.spy(validators, "validate_template")

        result = await transaction_template_service.get_template(existing_template.id, user_id)

        assert result == TransactionTemplateResponse.model_validate(existing_template)

        assert result.splits is None
        assert result.has_splits is False

        validate_template_spy.assert_called_once_with(
            transaction_template_service.transaction_template_repository,
            user_id,
            existing_template.id,
        )

        transaction_template_repo_mock.get_by_id.assert_called_once()

        transaction_template_split_repo_mock.get_by_template.assert_called_once_with(
            existing_template.id
        )

    async def test_get_template_with_splits(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
        existing_template: TransactionTemplate,
    ):
        user_id = existing_template.user_id

        existing_template.category_id = None

        splits = [
            make_transaction_template_split(
                id=1,
                transaction_template_id=existing_template.id,
                category_id=1,
                amount=Decimal("30.00"),
                description="Coffee",
            ),
            make_transaction_template_split(
                id=2,
                transaction_template_id=existing_template.id,
                category_id=2,
                amount=Decimal("20.00"),
                description="Croissant",
            ),
        ]

        transaction_template_repo_mock.get_by_id.return_value = existing_template
        transaction_template_split_repo_mock.get_by_template.return_value = splits

        result = await transaction_template_service.get_template(existing_template.id, user_id)

        assert result.has_splits is True

        assert result.splits == [
            TransactionTemplateSplitResponse.model_validate(split) for split in splits
        ]

        assert sum(split.amount for split in result.splits) == existing_template.amount

        transaction_template_split_repo_mock.get_by_template.assert_called_once_with(
            existing_template.id
        )

    async def test_get_template_not_found_template(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
    ):
        template_id = 999
        user_id = 1

        transaction_template_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Transaction template not found"):
            await transaction_template_service.get_template(template_id, user_id)

        transaction_template_repo_mock.get_by_id.assert_called_once()


class TestGetUserTemplates:
    @pytest.fixture
    def user_templates(self):
        return [
            make_transaction_template(
                id=1,
                name="Breakfast",
                description="Breakfast",
                amount=Decimal("200.00"),
            ),
            make_transaction_template(
                id=2,
                type=TransactionType.INCOME,
                name="Salary",
                description="Salary",
                amount=Decimal("25000.00"),
            ),
        ]

    async def test_get_user_templates_success(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
        user_templates: list[TransactionTemplate],
    ):
        user_id = 1

        limit = 20
        offset = 0

        transaction_template_repo_mock.get_by_user.return_value = user_templates
        transaction_template_split_repo_mock.get_template_ids_with_splits.return_value = set()

        result = await transaction_template_service.get_user_templates(user_id, limit, offset)

        assert result == [TransactionTemplateListItem.model_validate(t) for t in user_templates]

        transaction_template_repo_mock.get_by_user.assert_called_once_with(user_id, limit, offset)

        transaction_template_split_repo_mock.get_template_ids_with_splits.assert_called_once_with(
            [1, 2]
        )

    async def test_get_user_templates_marks_templates_with_splits(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
        user_templates: list[TransactionTemplate],
    ):
        """The flag comes from one set lookup: only the ids in it are marked."""
        user_id = 1

        limit = 20
        offset = 0

        transaction_template_repo_mock.get_by_user.return_value = user_templates
        transaction_template_split_repo_mock.get_template_ids_with_splits.return_value = {1}

        result = await transaction_template_service.get_user_templates(user_id, limit, offset)

        assert result[0].has_splits is True
        assert result[1].has_splits is False

        transaction_template_split_repo_mock.get_template_ids_with_splits.assert_called_once_with(
            [1, 2]
        )

    async def test_get_empty_user_templates(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        transaction_template_split_repo_mock: TransactionTemplateSplitRepository,
    ):
        user_id = 1

        user_templates = []

        limit = 20
        offset = 0

        transaction_template_repo_mock.get_by_user.return_value = user_templates

        result = await transaction_template_service.get_user_templates(user_id, limit, offset)

        assert result == [TransactionTemplateListItem.model_validate(t) for t in user_templates]

        transaction_template_repo_mock.get_by_user.assert_called_once_with(user_id, limit, offset)

        transaction_template_split_repo_mock.get_template_ids_with_splits.assert_not_called()
