from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pytest_mock import MockerFixture

from app.core import UnitOfWork
from app.core.exceptions import NotAllowedActionException, NotFoundException, ValueExistsException
from app.models import Category, Currency, TransactionTemplate, TransactionType
from app.repositories import CategoryRepository, CurrencyRepository, TransactionTemplateRepository
from app.schemas import (
    TransactionTemplateCreate,
    TransactionTemplateResponse,
    TransactionTemplateUpdate,
)
from app.services import TransactionTemplateService, validators
from tests.units.services.helpers import (
    as_persisted,
    assert_model_fields,
    make_transaction_template,
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

    async def test_update_template_archived_category(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_template: TransactionTemplate,
        existing_category: Category,
        data: TransactionTemplateUpdate,
    ):
        data.category_id = existing_category.id
        user_id = existing_template.user_id
        existing_category.archived_at = datetime.now(UTC)

        transaction_template_repo_mock.get_by_id.return_value = existing_template
        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        category_repo_mock.get_by_id.return_value = existing_category

        with pytest.raises(
            NotAllowedActionException, match="Archived category is not allowed to use"
        ):
            await transaction_template_service.update_template(existing_template.id, data, user_id)

        transaction_template_repo_mock.get_by_user_and_name.assert_called_once_with(
            data.name, user_id
        )

        category_repo_mock.get_by_id.assert_called_once_with(data.category_id)

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

    async def test_update_template_keeps_archived_category_allowed(
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
        user_id = existing_template.user_id

        data.category_id = existing_template.category_id
        data.currency_code = existing_template.currency_code

        existing_category.archived_at = datetime.now(UTC)

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        transaction_template_repo_mock.get_by_id.return_value = existing_template
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        transaction_template_repo_mock.update.return_value = existing_template

        validate_category_spy = mocker.spy(validators, "validate_category")

        await transaction_template_service.update_template(existing_template.id, data, user_id)

        validate_category_spy.assert_called_once_with(
            transaction_template_service.category_repository,
            user_id,
            data.category_id,
            allow_archived=True,
        )

        transaction_template_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_template_keeps_inactive_currency_allowed(
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
        user_id = existing_template.user_id

        data.category_id = existing_template.category_id
        data.currency_code = existing_template.currency_code

        existing_currency.is_active = False

        transaction_template_repo_mock.get_by_user_and_name.return_value = None
        transaction_template_repo_mock.get_by_id.return_value = existing_template
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        transaction_template_repo_mock.update.return_value = existing_template

        validate_currency_spy = mocker.spy(validators, "validate_currency")

        await transaction_template_service.update_template(existing_template.id, data, user_id)

        validate_currency_spy.assert_called_once_with(
            transaction_template_service.currency_repository,
            data.currency_code,
            allow_inactive=True,
        )

        transaction_template_repo_mock.update.assert_called_once()

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
        existing_template: TransactionTemplate,
    ):
        user_id = existing_template.user_id

        transaction_template_repo_mock.get_by_id.return_value = existing_template

        validate_template_spy = mocker.spy(validators, "validate_template")

        result = await transaction_template_service.get_template(existing_template.id, user_id)

        assert result == TransactionTemplateResponse.model_validate(existing_template)

        validate_template_spy.assert_called_once_with(
            transaction_template_service.transaction_template_repository,
            user_id,
            existing_template.id,
        )

        transaction_template_repo_mock.get_by_id.assert_called_once()

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
    async def test_get_user_templates_success(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
    ):
        user_id = 1

        user_templates = [
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

        limit = 20
        offset = 0

        transaction_template_repo_mock.get_by_user.return_value = user_templates

        result = await transaction_template_service.get_user_templates(user_id, limit, offset)

        assert result == [TransactionTemplateResponse.model_validate(t) for t in user_templates]

        transaction_template_repo_mock.get_by_user.assert_called_once_with(user_id, limit, offset)

    async def test_get_empty_user_templates(
        self,
        transaction_template_service: TransactionTemplateService,
        transaction_template_repo_mock: TransactionTemplateRepository,
    ):
        user_id = 1

        user_templates = []

        limit = 20
        offset = 0

        transaction_template_repo_mock.get_by_user.return_value = user_templates

        result = await transaction_template_service.get_user_templates(user_id, limit, offset)

        assert result == [TransactionTemplateResponse.model_validate(t) for t in user_templates]

        transaction_template_repo_mock.get_by_user.assert_called_once_with(user_id, limit, offset)
