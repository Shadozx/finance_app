from decimal import Decimal
from datetime import date

import pytest

from app.repositories import BudgetRepository, TransactionRepository, UserRepository
from app.models import Budget, Transaction, TransactionType, TransactionKind, User, Category, Currency


@pytest.fixture
async def budget(
        budget_repository: BudgetRepository,
        user: User,
        category: Category,
        uah_currency: Currency,
):
    return await budget_repository.create(Budget(
        name="Food July",
        amount=Decimal("5000.00"),
        currency_code=uah_currency.code,
        category_id=category.id,
        user_id=user.id,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
    ))


class TestCreate:
    async def test_create(
            self,
            budget_repository: BudgetRepository,
            user: User,
            category: Category,
            uah_currency: Currency,
    ):
        budget = Budget(
            name="Food July",
            amount=Decimal("5000.00"),
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=user.id,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )

        created = await budget_repository.create(budget)

        assert created.id is not None
        assert created.amount == budget.amount
        assert created.currency_code == budget.currency_code
        assert created.category_id == budget.category_id
        assert created.user_id == budget.user_id
        assert created.start_date == budget.start_date
        assert created.end_date == budget.end_date


class TestGetById:
    async def test_get_by_id(
            self,
            budget_repository: BudgetRepository,
            budget: Budget,
    ):
        found = await budget_repository.get_by_id(budget.id)

        assert found.id == budget.id
        assert found.amount == budget.amount
        assert found.user_id == budget.user_id

    async def test_get_by_id_not_found(
            self,
            budget_repository: BudgetRepository,
    ):
        found = await budget_repository.get_by_id(999)
        assert found is None


class TestUpdate:
    async def test_update(
            self,
            budget_repository: BudgetRepository,
            budget: Budget,
    ):
        budget.amount = Decimal("7000.00")

        updated = await budget_repository.update(budget)

        assert updated.id == budget.id
        assert updated.amount == Decimal("7000.00")

        found = await budget_repository.get_by_id(budget.id)
        assert found.amount == Decimal("7000.00")


class TestDelete:
    async def test_delete(
            self,
            budget_repository: BudgetRepository,
            budget: Budget,
    ):
        await budget_repository.delete(budget)

        found = await budget_repository.get_by_id(budget.id)
        assert found is None


class TestGetByPeriod:
    async def test_budget_fully_inside_period(
            self,
            budget_repository: BudgetRepository,
            budget: Budget,
            user: User,
    ):
        result = await budget_repository.get_by_period(
            user.id, date(2026, 7, 1), date(2026, 7, 31)
        )
        assert len(result) == 1
        assert result[0].id == budget.id

    async def test_budget_partial_overlap(
            self,
            budget_repository: BudgetRepository,
            user: User,
            category: Category,
            uah_currency: Currency,
    ):
        crossing = await budget_repository.create(Budget(
            amount=Decimal("3000.00"),
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=user.id,
            start_date=date(2026, 6, 15),
            end_date=date(2026, 7, 15),
        ))

        june = await budget_repository.get_by_period(
            user.id, date(2026, 6, 1), date(2026, 6, 30)
        )
        assert crossing.id in {b.id for b in june}

        july = await budget_repository.get_by_period(
            user.id, date(2026, 7, 1), date(2026, 7, 31)
        )
        assert crossing.id in {b.id for b in july}

    async def test_budget_outside_period_excluded(
            self,
            budget_repository: BudgetRepository,
            budget: Budget,
            user: User,
    ):
        result = await budget_repository.get_by_period(
            user.id, date(2026, 10, 1), date(2026, 10, 31)
        )
        assert budget.id not in {b.id for b in result}

    async def test_active_on_today_single_point(
            self,
            budget_repository: BudgetRepository,
            budget: Budget,
            user: User,
    ):
        result = await budget_repository.get_by_period(
            user.id, date(2026, 7, 15), date(2026, 7, 15)
        )
        assert budget.id in {b.id for b in result}

        result_aug = await budget_repository.get_by_period(
            user.id, date(2026, 8, 20), date(2026, 8, 20)
        )
        assert budget.id not in {b.id for b in result_aug}

    async def test_ordered_by_start_date(
            self,
            budget_repository: BudgetRepository,
            user: User,
            category: Category,
            uah_currency: Currency,
            usd_currency: Currency,
    ):
        b_mar = await budget_repository.create(Budget(
            amount=Decimal("100.00"), currency_code=uah_currency.code,
            category_id=category.id, user_id=user.id,
            start_date=date(2026, 3, 1), end_date=date(2026, 3, 31),
        ))
        b_jan = await budget_repository.create(Budget(
            amount=Decimal("100.00"), currency_code=usd_currency.code,
            category_id=category.id, user_id=user.id,
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
        ))

        result = await budget_repository.get_by_period(
            user.id, date(2026, 1, 1), date(2026, 12, 31)
        )

        ids = [b.id for b in result]
        assert ids.index(b_jan.id) < ids.index(b_mar.id)

    async def test_returns_only_own(
            self,
            budget_repository: BudgetRepository,
            user_repository: UserRepository,
            budget: Budget,
            user: User,
            category: Category,
            uah_currency: Currency,
    ):
        other_user = await user_repository.create(User(
            email="other@test.com", username="other", hashed_password="hashed",
        ))
        await budget_repository.create(Budget(
            amount=Decimal("9999.00"), currency_code=uah_currency.code,
            category_id=category.id, user_id=other_user.id,
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 31),
        ))

        result = await budget_repository.get_by_period(
            user.id, date(2026, 7, 1), date(2026, 7, 31)
        )

        assert len(result) == 1
        assert result[0].id == budget.id

    async def test_empty(
            self,
            budget_repository: BudgetRepository,
            user: User,
    ):
        result = await budget_repository.get_by_period(
            user.id, date(2026, 7, 1), date(2026, 7, 31)
        )
        assert len(result) == 0


class TestGetSpent:
    async def test_spent_sums_matching_expenses(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            category: Category,
            uah_currency: Currency,
    ):
        await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE, kind=TransactionKind.REGULAR, amount=Decimal("2000.00"),
            currency_code=uah_currency.code, category_id=category.id,
            user_id=user.id, date=date(2026, 7, 5),
        ))
        await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE, kind=TransactionKind.REGULAR, amount=Decimal("1000.00"),
            currency_code=uah_currency.code, category_id=category.id,
            user_id=user.id, date=date(2026, 7, 20),
        ))

        spent = await transaction_repository.get_spent(
            user.id, category.id, uah_currency.code,
            date(2026, 7, 1), date(2026, 7, 31),
        )

        assert spent == Decimal("3000.00")

    async def test_spent_ignores_income(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            category: Category,
            uah_currency: Currency,
    ):
        await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE, kind=TransactionKind.REGULAR, amount=Decimal("500.00"),
            currency_code=uah_currency.code, category_id=category.id,
            user_id=user.id, date=date(2026, 7, 5),
        ))
        await transaction_repository.create(Transaction(
            type=TransactionType.INCOME, kind=TransactionKind.REGULAR, amount=Decimal("10000.00"),
            currency_code=uah_currency.code, category_id=category.id,
            user_id=user.id, date=date(2026, 7, 10),
        ))

        spent = await transaction_repository.get_spent(
            user.id, category.id, uah_currency.code,
            date(2026, 7, 1), date(2026, 7, 31),
        )

        assert spent == Decimal("500.00")

    async def test_spent_filters_by_category_currency_dates(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            category: Category,
            uah_currency: Currency,
            usd_currency: Currency,
    ):
        await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE, kind=TransactionKind.REGULAR, amount=Decimal("300.00"),
            currency_code=uah_currency.code, category_id=category.id,
            user_id=user.id, date=date(2026, 7, 10),
        ))
        await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE, kind=TransactionKind.REGULAR, amount=Decimal("40.00"),
            currency_code=usd_currency.code, category_id=category.id,
            user_id=user.id, date=date(2026, 7, 10),
        ))
        await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE, kind=TransactionKind.REGULAR, amount=Decimal("999.00"),
            currency_code=uah_currency.code, category_id=None,
            user_id=user.id, date=date(2026, 7, 10),
        ))
        await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE, kind=TransactionKind.REGULAR, amount=Decimal("888.00"),
            currency_code=uah_currency.code, category_id=category.id,
            user_id=user.id, date=date(2026, 8, 1),
        ))

        spent = await transaction_repository.get_spent(
            user.id, category.id, uah_currency.code,
            date(2026, 7, 1), date(2026, 7, 31),
        )

        assert spent == Decimal("300.00")

    async def test_spent_returns_zero_when_empty(
            self,
            transaction_repository: TransactionRepository,
            user: User,
            category: Category,
            uah_currency: Currency,
    ):
        spent = await transaction_repository.get_spent(
            user.id, category.id, uah_currency.code,
            date(2026, 7, 1), date(2026, 7, 31),
        )

        assert spent == 0

    async def test_spent_returns_only_own(
            self,
            transaction_repository: TransactionRepository,
            user_repository: UserRepository,
            user: User,
            category: Category,
            uah_currency: Currency,
    ):
        other_user = await user_repository.create(User(
            email="other2@test.com", username="other2", hashed_password="hashed",
        ))
        await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE, kind=TransactionKind.REGULAR, amount=Decimal("777.00"),
            currency_code=uah_currency.code, category_id=category.id,
            user_id=other_user.id, date=date(2026, 7, 10),
        ))
        await transaction_repository.create(Transaction(
            type=TransactionType.EXPENSE, kind=TransactionKind.REGULAR, amount=Decimal("100.00"),
            currency_code=uah_currency.code, category_id=category.id,
            user_id=user.id, date=date(2026, 7, 10),
        ))

        spent = await transaction_repository.get_spent(
            user.id, category.id, uah_currency.code,
            date(2026, 7, 1), date(2026, 7, 31),
        )

        assert spent == Decimal("100.00")


class TestFindSameBudget:
    async def test_finds_exact_match(
            self,
            budget_repository: BudgetRepository,
            budget: Budget,
            user: User,
            category: Category,
            uah_currency: Currency,
    ):
        candidate = Budget(
            amount=Decimal("999.00"),
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=user.id,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )

        found = await budget_repository.find_same_budget(
            user.id,
            candidate.category_id,
            candidate.currency_code,
            candidate.start_date,
            candidate.end_date,
        )

        assert found is not None
        assert found.id == budget.id

    async def test_no_match_different_period(
            self,
            budget_repository: BudgetRepository,
            budget: Budget,
            user: User,
            category: Category,
            uah_currency: Currency,
    ):
        candidate = Budget(
            amount=Decimal("5000.00"),
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=user.id,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
        )

        found = await budget_repository.find_same_budget(
            user.id,
            candidate.category_id,
            candidate.currency_code,
            candidate.start_date,
            candidate.end_date,
        )

        assert found is None

    async def test_no_match_different_currency(
            self,
            budget_repository: BudgetRepository,
            budget: Budget,
            user: User,
            category: Category,
            usd_currency: Currency,
    ):
        candidate = Budget(
            amount=Decimal("5000.00"),
            currency_code=usd_currency.code,
            category_id=category.id,
            user_id=user.id,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )

        found = await budget_repository.find_same_budget(
            user.id,
            candidate.category_id,
            candidate.currency_code,
            candidate.start_date,
            candidate.end_date,
        )

        assert found is None

    async def test_no_match_other_user(
            self,
            budget_repository: BudgetRepository,
            user_repository: UserRepository,
            budget: Budget,
            category: Category,
            uah_currency: Currency,
    ):
        other_user = await user_repository.create(User(
            email="other3@test.com", username="other3", hashed_password="hashed",
        ))
        candidate = Budget(
            amount=Decimal("5000.00"),
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=other_user.id,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )

        found = await budget_repository.find_same_budget(
            other_user.id,
            candidate.category_id,
            candidate.currency_code,
            candidate.start_date,
            candidate.end_date,
        )
        assert found is None


class TestGetByPeriodEdges:
    async def test_active_on_first_day_of_budget(
            self,
            budget_repository: BudgetRepository,
            budget: Budget,
            user: User,
    ):
        result = await budget_repository.get_by_period(
            user.id, date(2026, 7, 1), date(2026, 7, 1)
        )
        assert budget.id in {b.id for b in result}

    async def test_active_on_last_day_of_budget(
            self,
            budget_repository: BudgetRepository,
            budget: Budget,
            user: User,
    ):
        result = await budget_repository.get_by_period(
            user.id, date(2026, 7, 31), date(2026, 7, 31)
        )
        assert budget.id in {b.id for b in result}

    async def test_not_active_day_before_start(
            self,
            budget_repository: BudgetRepository,
            budget: Budget,
            user: User,
    ):
        result = await budget_repository.get_by_period(
            user.id, date(2026, 6, 30), date(2026, 6, 30)
        )
        assert budget.id not in {b.id for b in result}

    async def test_not_active_day_after_end(
            self,
            budget_repository: BudgetRepository,
            budget: Budget,
            user: User,
    ):
        result = await budget_repository.get_by_period(
            user.id, date(2026, 8, 1), date(2026, 8, 1)
        )
        assert budget.id not in {b.id for b in result}

    async def test_single_day_budget(
            self,
            budget_repository: BudgetRepository,
            user: User,
            category: Category,
            uah_currency: Currency,
    ):
        one_day = await budget_repository.create(Budget(
            amount=Decimal("100.00"),
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=user.id,
            start_date=date(2026, 7, 15),
            end_date=date(2026, 7, 15),
        ))

        result = await budget_repository.get_by_period(
            user.id, date(2026, 7, 15), date(2026, 7, 15)
        )
        assert one_day.id in {b.id for b in result}

        result_next = await budget_repository.get_by_period(
            user.id, date(2026, 7, 16), date(2026, 7, 16)
        )
        assert one_day.id not in {b.id for b in result_next}

    async def test_budget_wider_than_search_period(
            self,
            budget_repository: BudgetRepository,
            user: User,
            category: Category,
            uah_currency: Currency,
    ):
        yearly = await budget_repository.create(Budget(
            amount=Decimal("50000.00"),
            currency_code=uah_currency.code,
            category_id=category.id,
            user_id=user.id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        ))

        result = await budget_repository.get_by_period(
            user.id, date(2026, 5, 10), date(2026, 5, 17)
        )
        assert yearly.id in {b.id for b in result}


class TestFindSameBudgetKeyFields:
    async def test_no_match_different_category(
            self,
            budget_repository: BudgetRepository,
            category_repository,
            budget: Budget,
            user: User,
            uah_currency: Currency,
    ):
        other_category = await category_repository.create(
            Category(name="Transport", user_id=user.id)
        )

        candidate = Budget(
            amount=Decimal("5000.00"),
            currency_code=uah_currency.code,
            category_id=other_category.id,
            user_id=user.id,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )

        found = await budget_repository.find_same_budget(
            user.id,
            candidate.category_id,
            candidate.currency_code,
            candidate.start_date,
            candidate.end_date,
        )

        assert found is None


