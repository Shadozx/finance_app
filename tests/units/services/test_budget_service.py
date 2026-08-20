from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pytest_mock import MockerFixture

from app.core import UnitOfWork
from app.core.exceptions import (
    NotAllowedActionException,
    NotFoundException,
    PermissionException,
    ValueExistsException,
)
from app.models import Budget, Category, Currency
from app.repositories import (
    BudgetRepository,
    CategoryRepository,
    CurrencyRepository,
    TransactionRepository,
)
from app.schemas import BudgetCreate, BudgetFilters, BudgetResponse, BudgetUpdate
from app.services import BudgetService, validators
from tests.units.services.helpers import as_persisted, assert_model_fields, make_budget


class TestGetBudget:
    async def test_get_budget_success(
        self,
        mocker: MockerFixture,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        existing_budget: Budget,
    ):
        user_id = existing_budget.user_id
        budget_id = existing_budget.id

        budget_repo_mock.get_by_id.return_value = existing_budget

        validate_budget_spy = mocker.spy(validators, "validate_budget")

        result = await budget_service.get_budget(budget_id, user_id)

        assert result == BudgetResponse.model_validate(existing_budget)

        validate_budget_spy.assert_called_once_with(
            budget_service.budget_repository,
            user_id,
            budget_id,
        )
        budget_repo_mock.get_by_id.assert_called_once()

    async def test_get_budget_not_found(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
    ):
        budget_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Budget not found"):
            await budget_service.get_budget(999, 1)

        budget_repo_mock.get_by_id.assert_called_once()

    async def test_get_budget_wrong_owner(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        existing_budget: Budget,
    ):
        budget_repo_mock.get_by_id.return_value = existing_budget
        wrong_user_id = existing_budget.user_id + 1

        with pytest.raises(PermissionException, match="You don't have permission to this budget"):
            await budget_service.get_budget(existing_budget.id, wrong_user_id)


class TestCreateBudget:
    @pytest.fixture
    def data(
        self,
        existing_budget: Budget,
    ) -> BudgetCreate:
        return BudgetCreate(
            name=existing_budget.name,
            amount=existing_budget.amount,
            currency_code=existing_budget.currency_code,
            category_id=existing_budget.category_id,
            start_date=existing_budget.start_date,
            end_date=existing_budget.end_date,
        )

    async def test_create_budget_success(
        self,
        mocker: MockerFixture,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_currency: Currency,
        existing_category: Category,
        data: BudgetCreate,
    ):
        user_id = existing_category.user_id
        data.category_id = existing_category.id

        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = existing_category
        budget_repo_mock.find_same_budget.return_value = None

        budget_repo_mock.add.side_effect = as_persisted

        validate_category_spy = mocker.spy(validators, "validate_category")
        validate_currency_spy = mocker.spy(validators, "validate_currency")

        result = await budget_service.create_budget(data, user_id)

        call_args = budget_repo_mock.add.call_args[0][0]

        assert result == BudgetResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            amount=data.amount,
            currency_code=data.currency_code,
            category_id=data.category_id,
            start_date=data.start_date,
            end_date=data.end_date,
            user_id=user_id,
        )

        validate_category_spy.assert_called_once_with(
            budget_service.category_repository,
            user_id,
            existing_category.id,
        )
        validate_currency_spy.assert_called_once_with(
            budget_service.currency_repository,
            existing_currency.code,
        )

        budget_repo_mock.find_same_budget.assert_called_once_with(
            user_id,
            data.category_id,
            data.currency_code,
            data.start_date,
            data.end_date,
        )

        budget_repo_mock.add.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_create_budget_duplicate(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_currency: Currency,
        existing_category: Category,
        existing_budget: Budget,
        data: BudgetCreate,
    ):
        user_id = existing_category.user_id
        data.category_id = existing_category.id

        currency_repo_mock.get_by_code.return_value = existing_currency
        category_repo_mock.get_by_id.return_value = existing_category
        budget_repo_mock.find_same_budget.return_value = existing_budget

        with pytest.raises(ValueExistsException, match="already exists"):
            await budget_service.create_budget(data, user_id)

        budget_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_budget_archived_category(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_category: Category,
        data: BudgetCreate,
    ):
        data.category_id = existing_category.id
        existing_category.archived_at = datetime.now(timezone.utc)

        category_repo_mock.get_by_id.return_value = existing_category
        budget_repo_mock.find_same_budget.return_value = None

        with pytest.raises(
            NotAllowedActionException, match="Archived category is not allowed to use"
        ):
            await budget_service.create_budget(data, existing_category.user_id)

        budget_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_create_budget_inactive_currency(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_currency: Currency,
        existing_category: Category,
        data: BudgetCreate,
    ):
        data.category_id = existing_category.id
        existing_currency.is_active = False

        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        budget_repo_mock.find_same_budget.return_value = None

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await budget_service.create_budget(data, existing_category.user_id)

        budget_repo_mock.add.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()


class TestUpdateBudget:
    @pytest.fixture
    def data(
        self,
        existing_budget: Budget,
    ) -> BudgetUpdate:
        return BudgetUpdate(
            name="Updated budget",
            amount=Decimal("7000.00"),
            currency_code=existing_budget.currency_code,
            category_id=existing_budget.category_id,
            start_date=existing_budget.start_date,
            end_date=existing_budget.end_date,
        )

    async def test_update_budget_success(
        self,
        mocker: MockerFixture,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_budget: Budget,
        existing_currency: Currency,
        existing_category: Category,
        data: BudgetUpdate,
    ):
        data.category_id = existing_category.id
        user_id = existing_budget.user_id

        budget_repo_mock.get_by_id.return_value = existing_budget
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        budget_repo_mock.find_same_budget.return_value = None

        budget_repo_mock.update.side_effect = as_persisted

        validate_budget_spy = mocker.spy(validators, "validate_budget")
        validate_category_spy = mocker.spy(validators, "validate_category")
        validate_currency_spy = mocker.spy(validators, "validate_currency")

        result = await budget_service.update_budget(existing_budget.id, data, user_id)

        call_args = budget_repo_mock.update.call_args[0][0]

        assert result == BudgetResponse.model_validate(call_args)

        assert_model_fields(
            call_args,
            amount=data.amount,
            currency_code=data.currency_code,
            category_id=data.category_id,
            start_date=data.start_date,
            end_date=data.end_date,
            user_id=user_id,
        )

        validate_budget_spy.assert_called_once_with(
            budget_service.budget_repository,
            user_id,
            existing_budget.id,
        )
        validate_category_spy.assert_called_once_with(
            budget_service.category_repository,
            user_id,
            existing_category.id,
            allow_archived=True,
        )
        validate_currency_spy.assert_called_once_with(
            budget_service.currency_repository,
            existing_currency.code,
            allow_inactive=True,
        )

        budget_repo_mock.find_same_budget.assert_called_once_with(
            user_id,
            data.category_id,
            data.currency_code,
            data.start_date,
            data.end_date,
        )

        budget_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_budget_not_found(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        unit_of_work_mock: UnitOfWork,
        data: BudgetUpdate,
    ):
        budget_repo_mock.find_same_budget.return_value = None
        budget_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Budget not found"):
            await budget_service.update_budget(999, data, 1)

        budget_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_budget_duplicate_not_self(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_budget: Budget,
        existing_currency: Currency,
        existing_category: Category,
        data: BudgetUpdate,
    ):
        data.category_id = existing_category.id
        user_id = existing_budget.user_id

        budget_repo_mock.get_by_id.return_value = existing_budget
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency

        other_budget = make_budget(
            id=existing_budget.id + 1,
            name="Other",
            amount=Decimal("100.00"),
            currency_code=existing_budget.currency_code,
            category_id=existing_category.id,
            start_date=existing_budget.start_date,
            end_date=existing_budget.end_date,
            user_id=user_id,
        )
        budget_repo_mock.find_same_budget.return_value = other_budget

        with pytest.raises(
            ValueExistsException,
            match="Budget for this category, currency and period already exists",
        ):
            await budget_service.update_budget(existing_budget.id, data, user_id)

        budget_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_budget_duplicate_is_self_allowed(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        currency_repo_mock: CurrencyRepository,
        category_repo_mock: CategoryRepository,
        unit_of_work_mock: UnitOfWork,
        existing_budget: Budget,
        existing_currency: Currency,
        existing_category: Category,
        data: BudgetUpdate,
    ):
        data.category_id = existing_category.id
        user_id = existing_budget.user_id

        budget_repo_mock.get_by_id.return_value = existing_budget
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        budget_repo_mock.find_same_budget.return_value = existing_budget
        budget_repo_mock.update.return_value = existing_budget

        result = await budget_service.update_budget(existing_budget.id, data, user_id)

        assert result == BudgetResponse.model_validate(existing_budget)
        budget_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_budget_keeps_archived_category_allowed(
        self,
        mocker: MockerFixture,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        category_repo_mock: CategoryRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_budget: Budget,
        existing_category: Category,
        existing_currency: Currency,
        data: BudgetUpdate,
    ):
        data.category_id = existing_budget.category_id
        data.currency_code = existing_budget.currency_code

        existing_category.archived_at = datetime.now(timezone.utc)

        budget_repo_mock.find_same_budget.return_value = None
        budget_repo_mock.get_by_id.return_value = existing_budget
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        budget_repo_mock.update.return_value = existing_budget

        validate_category_spy = mocker.spy(validators, "validate_category")

        await budget_service.update_budget(
            existing_budget.id,
            data,
            existing_budget.user_id,
        )

        validate_category_spy.assert_called_once_with(
            budget_service.category_repository,
            existing_budget.user_id,
            data.category_id,
            allow_archived=True,
        )

        budget_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_budget_keeps_inactive_currency_allowed(
        self,
        mocker: MockerFixture,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        category_repo_mock: CategoryRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_budget: Budget,
        existing_category: Category,
        existing_currency: Currency,
        data: BudgetUpdate,
    ):
        data.category_id = existing_budget.category_id
        data.currency_code = existing_budget.currency_code

        existing_currency.is_active = False

        budget_repo_mock.find_same_budget.return_value = None
        budget_repo_mock.get_by_id.return_value = existing_budget
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency
        budget_repo_mock.update.return_value = existing_budget

        validate_currency_spy = mocker.spy(validators, "validate_currency")

        await budget_service.update_budget(
            existing_budget.id,
            data,
            existing_budget.user_id,
        )

        validate_currency_spy.assert_called_once_with(
            budget_service.currency_repository,
            data.currency_code,
            allow_inactive=True,
        )

        budget_repo_mock.update.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_update_budget_to_archived_category_fails(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        category_repo_mock: CategoryRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_budget: Budget,
        existing_category: Category,
        existing_currency: Currency,
        data: BudgetUpdate,
    ):
        data.category_id = existing_budget.category_id + 1
        existing_category.id = data.category_id
        existing_category.archived_at = datetime.now(timezone.utc)

        budget_repo_mock.find_same_budget.return_value = None
        budget_repo_mock.get_by_id.return_value = existing_budget
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency

        with pytest.raises(
            NotAllowedActionException, match="Archived category is not allowed to use"
        ):
            await budget_service.update_budget(
                existing_budget.id,
                data,
                existing_budget.user_id,
            )

        budget_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()

    async def test_update_budget_to_inactive_currency_fails(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        category_repo_mock: CategoryRepository,
        currency_repo_mock: CurrencyRepository,
        unit_of_work_mock: UnitOfWork,
        existing_budget: Budget,
        existing_category: Category,
        existing_currency: Currency,
        data: BudgetUpdate,
    ):
        data.category_id = existing_budget.category_id
        data.currency_code = "USD"
        existing_currency.code = "USD"
        existing_currency.is_active = False

        budget_repo_mock.find_same_budget.return_value = None
        budget_repo_mock.get_by_id.return_value = existing_budget
        category_repo_mock.get_by_id.return_value = existing_category
        currency_repo_mock.get_by_code.return_value = existing_currency

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await budget_service.update_budget(
                existing_budget.id,
                data,
                existing_budget.user_id,
            )

        budget_repo_mock.update.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()


class TestDeleteBudget:
    async def test_delete_budget_success(
        self,
        mocker: MockerFixture,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        unit_of_work_mock: UnitOfWork,
        existing_budget: Budget,
    ):
        budget_repo_mock.get_by_id.return_value = existing_budget

        validate_budget_spy = mocker.spy(validators, "validate_budget")

        await budget_service.delete_budget(existing_budget.id, existing_budget.user_id)

        validate_budget_spy.assert_called_once()

        budget_repo_mock.delete.assert_called_once()

        unit_of_work_mock.commit.assert_awaited_once()

    async def test_delete_budget_not_found(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        unit_of_work_mock: UnitOfWork,
    ):
        budget_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Budget not found"):
            await budget_service.delete_budget(999, 1)

        budget_repo_mock.delete.assert_not_called()

        unit_of_work_mock.commit.assert_not_awaited()


class TestGetUserBudgets:
    async def test_get_user_budgets_default_active(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        existing_budget: Budget,
    ):
        budget_repo_mock.get_by_period.return_value = [existing_budget]

        filters = BudgetFilters()
        result = await budget_service.get_user_budgets(existing_budget.user_id, filters)

        assert result == [BudgetResponse.model_validate(existing_budget)]

        call_args = budget_repo_mock.get_by_period.call_args[0]
        assert call_args[1] == call_args[2]

    async def test_get_user_budgets_with_period(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        existing_budget: Budget,
    ):
        budget_repo_mock.get_by_period.return_value = [existing_budget]

        filters = BudgetFilters(
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
        result = await budget_service.get_user_budgets(existing_budget.user_id, filters)

        assert result == [BudgetResponse.model_validate(existing_budget)]

        budget_repo_mock.get_by_period.assert_called_once_with(
            existing_budget.user_id,
            date(2026, 7, 1),
            date(2026, 7, 31),
        )


class TestGetBudgetStatus:
    async def test_status_normal(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        transaction_repo_mock: TransactionRepository,
        existing_budget: Budget,
    ):
        budget_repo_mock.get_by_id.return_value = existing_budget
        transaction_repo_mock.get_spent.return_value = Decimal("3000.00")

        result = await budget_service.get_budget_status(existing_budget.id, existing_budget.user_id)

        assert result.spent == Decimal("3000.00")
        assert result.remaining == Decimal("2000.00")
        assert result.percent == Decimal("60.00")
        assert result.is_exceeded is False

    async def test_status_exceeded(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        transaction_repo_mock: TransactionRepository,
        existing_budget: Budget,
    ):
        budget_repo_mock.get_by_id.return_value = existing_budget
        transaction_repo_mock.get_spent.return_value = Decimal("6000.00")

        result = await budget_service.get_budget_status(existing_budget.id, existing_budget.user_id)

        assert result.spent == Decimal("6000.00")
        assert result.remaining == Decimal("-1000.00")
        assert result.percent == Decimal("120.00")
        assert result.is_exceeded is True

    async def test_status_exactly_full(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        transaction_repo_mock: TransactionRepository,
        existing_budget: Budget,
    ):
        budget_repo_mock.get_by_id.return_value = existing_budget
        transaction_repo_mock.get_spent.return_value = Decimal("5000.00")

        result = await budget_service.get_budget_status(existing_budget.id, existing_budget.user_id)

        assert result.remaining == Decimal("0.00")
        assert result.percent == Decimal("100.00")
        assert result.is_exceeded is False

    async def test_status_nothing_spent(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        transaction_repo_mock: TransactionRepository,
        existing_budget: Budget,
    ):
        budget_repo_mock.get_by_id.return_value = existing_budget
        transaction_repo_mock.get_spent.return_value = Decimal("0")

        result = await budget_service.get_budget_status(existing_budget.id, existing_budget.user_id)

        assert result.spent == Decimal("0")
        assert result.remaining == Decimal("5000.00")
        assert result.percent == Decimal("0")
        assert result.is_exceeded is False

    async def test_status_zero_limit_no_spend(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        transaction_repo_mock: TransactionRepository,
        zero_budget: Budget,
    ):
        budget_repo_mock.get_by_id.return_value = zero_budget
        transaction_repo_mock.get_spent.return_value = Decimal("0")

        result = await budget_service.get_budget_status(zero_budget.id, zero_budget.user_id)

        assert result.percent == Decimal("0")
        assert result.is_exceeded is False

    async def test_status_zero_limit_with_spend(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
        transaction_repo_mock: TransactionRepository,
        zero_budget: Budget,
    ):
        budget_repo_mock.get_by_id.return_value = zero_budget
        transaction_repo_mock.get_spent.return_value = Decimal("50.00")

        result = await budget_service.get_budget_status(zero_budget.id, zero_budget.user_id)

        assert result.percent == Decimal("100")
        assert result.is_exceeded is True

    async def test_status_not_found(
        self,
        budget_service: BudgetService,
        budget_repo_mock: BudgetRepository,
    ):
        budget_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Budget not found"):
            await budget_service.get_budget_status(999, 1)
