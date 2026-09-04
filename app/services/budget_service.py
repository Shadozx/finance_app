from datetime import date
from decimal import Decimal

import structlog

from app.core import UnitOfWork
from app.core.exceptions import ValueExistsException
from app.models import Budget
from app.repositories import (
    BudgetRepository,
    CategoryRepository,
    CurrencyRepository,
    TransactionRepository,
)
from app.schemas import (
    BudgetCreate,
    BudgetFilters,
    BudgetResponse,
    BudgetStatusResponse,
    BudgetUpdate,
)
from app.services import validators

logger = structlog.get_logger()


class BudgetService:
    def __init__(
        self,
        budget_repository: BudgetRepository,
        transaction_repository: TransactionRepository,
        category_repository: CategoryRepository,
        currency_repository: CurrencyRepository,
        unit_of_work: UnitOfWork,
    ):
        self.budget_repository = budget_repository
        self.transaction_repository = transaction_repository
        self.category_repository = category_repository
        self.currency_repository = currency_repository
        self.unit_of_work = unit_of_work

    async def get_budget(
        self,
        budget_id: int,
        user_id: int,
    ) -> BudgetResponse:
        existing_budget = await validators.validate_budget(
            self.budget_repository, user_id, budget_id
        )
        return BudgetResponse.model_validate(existing_budget)

    async def get_user_budgets(
        self,
        user_id: int,
        filters: BudgetFilters,
    ) -> list[BudgetResponse]:
        if filters.start_date is not None and filters.end_date is not None:
            start_date, end_date = filters.start_date, filters.end_date
        else:
            today = date.today()
            start_date, end_date = today, today

        budgets = await self.budget_repository.get_by_period(
            user_id,
            start_date,
            end_date,
            currency_code=filters.currency_code,
            category_id=filters.category_id,
        )
        return [BudgetResponse.model_validate(b) for b in budgets]

    async def create_budget(
        self,
        data: BudgetCreate,
        user_id: int,
    ) -> BudgetResponse:
        if await self.budget_repository.find_same_budget(
            user_id, data.category_id, data.currency_code, data.start_date, data.end_date
        ):
            raise ValueExistsException(
                "Budget for this category, currency and period already exists"
            )

        await validators.validate_category(self.category_repository, user_id, data.category_id)
        await validators.validate_currency(self.currency_repository, data.currency_code)

        new_budget = Budget(
            name=data.name,
            amount=data.amount,
            currency_code=data.currency_code,
            category_id=data.category_id,
            start_date=data.start_date,
            end_date=data.end_date,
            user_id=user_id,
        )

        created_budget = await self.budget_repository.add(new_budget)

        await self.unit_of_work.commit()

        logger.info("budget_create_success", user_id=user_id, budget_id=created_budget.id)

        return BudgetResponse.model_validate(created_budget)

    async def update_budget(
        self,
        budget_id: int,
        data: BudgetUpdate,
        user_id: int,
    ) -> BudgetResponse:
        duplicate = await self.budget_repository.find_same_budget(
            user_id, data.category_id, data.currency_code, data.start_date, data.end_date
        )
        if duplicate and duplicate.id != budget_id:
            raise ValueExistsException(
                "Budget for this category, currency and period already exists"
            )

        existing_budget = await validators.validate_budget(
            self.budget_repository, user_id, budget_id
        )

        category_changed = data.category_id != existing_budget.category_id
        currency_changed = data.currency_code != existing_budget.currency_code

        await validators.validate_category(
            self.category_repository,
            user_id,
            data.category_id,
            allow_archived=not category_changed,
        )

        await validators.validate_currency(
            self.currency_repository,
            data.currency_code,
            allow_inactive=not currency_changed,
        )

        existing_budget.name = data.name
        existing_budget.amount = data.amount
        existing_budget.currency_code = data.currency_code
        existing_budget.category_id = data.category_id
        existing_budget.start_date = data.start_date
        existing_budget.end_date = data.end_date

        updated_budget = await self.budget_repository.update(existing_budget)

        await self.unit_of_work.commit()

        logger.info("budget_update_success", user_id=user_id, budget_id=updated_budget.id)

        return BudgetResponse.model_validate(updated_budget)

    async def delete_budget(
        self,
        budget_id: int,
        user_id: int,
    ) -> None:
        existing_budget = await validators.validate_budget(
            self.budget_repository, user_id, budget_id
        )
        await self.budget_repository.delete(existing_budget)

        await self.unit_of_work.commit()

        logger.info("budget_delete_success", user_id=user_id, budget_id=existing_budget.id)

    async def get_budget_status(
        self,
        budget_id: int,
        user_id: int,
    ) -> BudgetStatusResponse:
        budget = await validators.validate_budget(self.budget_repository, user_id, budget_id)

        spent = await self.transaction_repository.get_spent(
            user_id,
            budget.category_id,
            budget.currency_code,
            budget.start_date,
            budget.end_date,
        )

        remaining = budget.amount - spent

        if budget.amount != Decimal("0"):
            percent = (spent / budget.amount) * 100
        elif spent == 0:
            percent = Decimal("0")
        else:
            percent = Decimal("100")

        is_exceeded = spent > budget.amount

        return BudgetStatusResponse(
            spent=spent,
            remaining=remaining,
            percent=percent,
            is_exceeded=is_exceeded,
            budget=BudgetResponse.model_validate(budget),
        )
