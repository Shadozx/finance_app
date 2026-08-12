from datetime import datetime, timezone
from decimal import Decimal
import pytest

from app.models import Category, Currency, Transaction, TransactionTemplate, Budget, Account, User
from app.repositories import (
    CategoryRepository,
    CurrencyRepository,
    TransactionTemplateRepository,
    TransactionRepository,
    BudgetRepository
)
from app.services.validators import (
    validate_category,
    validate_currency,
    validate_transaction,
    validate_template,
    validate_budget,
    resolve_settled_amount
)
from app.core.exceptions import (
    NotFoundException,
    PermissionException,
    NotAllowedActionException
)
from tests.units.services.helpers import assert_model_fields


class TestValidateCategory:

    async def test_validate_category_success(
            self,
            category_repo_mock: CategoryRepository,
            existing_category: Category
    ):
        """
        GIVEN: Category exists, owned by user, not archived
        WHEN: validate_category called
        THEN: Returns the same category instance
        """

        category_repo_mock.get_by_id.return_value = existing_category

        result = await validate_category(category_repo_mock, existing_category.user_id, existing_category.id)

        assert result is existing_category

        assert_model_fields(
            result,
            id=existing_category.id,
            name=existing_category.name,
            user_id=existing_category.user_id,
        )

        category_repo_mock.get_by_id.assert_called_once_with(
            existing_category.id
        )

    async def test_validate_category_without_category(
            self,
            category_repo_mock: CategoryRepository,
    ):
        """
        GIVEN: category_id is None
        WHEN: validate_category called
        THEN: Returns None, no repository call
        """

        category_repo_mock.get_by_id.return_value = None

        result = await validate_category(category_repo_mock, 1, None)

        assert result is None

        category_repo_mock.get_by_id.assert_not_called()

    async def test_validate_category_not_found_category(
            self,
            category_repo_mock: CategoryRepository,
    ):
        """
        GIVEN: Category doesn't exist
        WHEN: validate_category called
        THEN: NotFoundException raised
        """

        wrong_category_id = 999
        category_repo_mock.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="Category not found"):
            await validate_category(category_repo_mock, 1, wrong_category_id)

        category_repo_mock.get_by_id.assert_called_once_with(
            wrong_category_id
        )

    async def test_validate_category_wrong_owner(
            self,
            category_repo_mock: CategoryRepository,
            existing_category: Category
    ):
        """
        GIVEN: Category exists but owned by different user
        WHEN: validate_category called with wrong user_id
        THEN: PermissionException raised
        """

        category_repo_mock.get_by_id.return_value = existing_category

        wrong_user_id = existing_category.user_id + 1

        with pytest.raises(PermissionException, match="You don't have permission to this category"):
            await validate_category(category_repo_mock, wrong_user_id, existing_category.id)

        category_repo_mock.get_by_id.assert_called_once_with(
            existing_category.id
        )

    async def test_validate_category_archived_category(
            self,
            category_repo_mock: CategoryRepository,
            existing_category: Category
    ):
        """
        GIVEN: Category exists but is archived
        WHEN: validate_category called
        THEN: NotAllowedActionException raised
        """

        category_repo_mock.get_by_id.return_value = existing_category
        existing_category.archived_at = datetime.now(timezone.utc)

        with pytest.raises(NotAllowedActionException, match="Archived category is not allowed to use"):
            await validate_category(category_repo_mock, existing_category.user_id, existing_category.id)

        category_repo_mock.get_by_id.assert_called_once_with(
            existing_category.id
        )


class TestValidateCurrency:
    async def test_validate_currency_success(
            self,
            currency_repo_mock: CurrencyRepository,
            existing_currency: Currency
    ):
        """
        GIVEN: Currency exists and is active
        WHEN: validate_currency called
        THEN: Returns the same currency instance
        """
        currency_repo_mock.get_by_code.return_value = existing_currency

        result = await validate_currency(currency_repo_mock, existing_currency.code)

        assert result is existing_currency

        assert_model_fields(
            result,
            code=existing_currency.code,
            symbol=existing_currency.symbol,
            name=existing_currency.name,
            is_active=existing_currency.is_active,
        )

        currency_repo_mock.get_by_code.assert_called_once_with(
            existing_currency.code
        )

    async def test_validate_currency_not_found(
            self,
            currency_repo_mock: CurrencyRepository,
    ):
        """
        GIVEN: Currency doesn't exist
        WHEN: validate_currency called
        THEN: NotFoundException raised
        """

        currency_repo_mock.get_by_code.return_value = None

        wrong_currency_code = "UAH"

        with pytest.raises(NotFoundException, match="Currency not found"):
            await validate_currency(currency_repo_mock, wrong_currency_code)

        currency_repo_mock.get_by_code.assert_called_once_with(
            wrong_currency_code
        )

    async def test_validate_currency_inactive(
            self,
            currency_repo_mock: CurrencyRepository,
            existing_currency: Currency
    ):
        """
        GIVEN: Currency is inactive
        WHEN: validate_currency called
        THEN: NotAllowedActionException raised
        """

        existing_currency.is_active = False
        currency_repo_mock.get_by_code.return_value = existing_currency

        with pytest.raises(NotAllowedActionException, match="Currency is not active"):
            await validate_currency(currency_repo_mock, existing_currency.code)

        currency_repo_mock.get_by_code.assert_called_once_with(
            existing_currency.code
        )


class TestValidateTransaction:
    async def test_validate_transaction_success(
            self,
            transaction_repo_mock: TransactionRepository,
            existing_transaction: Transaction
    ):
        """
        GIVEN: Transaction exists, owned by user
        WHEN: validate_transaction called
        THEN: Returns the same transaction instance
        """

        transaction_repo_mock.get_by_id.return_value = existing_transaction

        result = await validate_transaction(transaction_repo_mock, existing_transaction.user_id,
                                            existing_transaction.id)

        assert result is existing_transaction

        assert_model_fields(
            result,
            id=existing_transaction.id,
            amount=existing_transaction.amount,
            description=existing_transaction.description,
            user_id=existing_transaction.user_id,
            currency_code=existing_transaction.currency_code,
        )

        transaction_repo_mock.get_by_id.assert_called_once_with(
            existing_transaction.id
        )

    async def test_validate_transaction_not_found(
            self,
            transaction_repo_mock: TransactionRepository,
            existing_transaction: Transaction
    ):
        """
        GIVEN: Transaction doesn't exist
        WHEN: validate_transaction called
        THEN: NotFoundException raised
        """

        transaction_repo_mock.get_by_id.return_value = None

        wrong_transaction_id = 999

        with pytest.raises(NotFoundException, match="Transaction not found"):
            await validate_transaction(transaction_repo_mock, 1, wrong_transaction_id)

        transaction_repo_mock.get_by_id.assert_called_once_with(
            wrong_transaction_id
        )

    async def test_validate_transaction_wrong_owner(
            self,
            transaction_repo_mock: TransactionRepository,
            existing_transaction: Transaction
    ):
        """
        GIVEN: Transaction exists but owned by different user
        WHEN: validate_transaction called with wrong user_id
        THEN: PermissionException raised
        """

        transaction_repo_mock.get_by_id.return_value = existing_transaction

        wrong_user_id = existing_transaction.user_id + 1

        with pytest.raises(PermissionException, match="You don't have permission to this transaction"):
            await validate_transaction(transaction_repo_mock, wrong_user_id, existing_transaction.id)

        transaction_repo_mock.get_by_id.assert_called_once_with(
            existing_transaction.id
        )


class TestValidateTemplate:
    async def test_validate_template_success(
            self,
            transaction_template_repo_mock: TransactionTemplateRepository,
            existing_template: TransactionTemplate
    ):
        """
        GIVEN: Transaction template exists, owned by user
        WHEN: validate_template called
        THEN: Returns the same transaction instance
        """

        transaction_template_repo_mock.get_by_id.return_value = existing_template

        result = await validate_template(
            transaction_template_repo_mock,
            existing_template.user_id,
            existing_template.id
        )

        assert result is existing_template

        assert_model_fields(
            result,
            id=existing_template.id,
            name=existing_template.name,
            amount=existing_template.amount,
            description=existing_template.description,
            user_id=existing_template.user_id,
            currency_code=existing_template.currency_code,
        )

        transaction_template_repo_mock.get_by_id.assert_called_once_with(
            existing_template.id
        )

    async def test_validate_template_not_found(
            self,
            transaction_template_repo_mock: TransactionTemplateRepository,
    ):
        """
        GIVEN: Transaction template doesn't exist
        WHEN: validate_template called
        THEN: NotFoundException raised
        """

        transaction_template_repo_mock.get_by_id.return_value = None

        wrong_template_id = 999

        with pytest.raises(NotFoundException, match="Transaction template not found"):
            await validate_template(transaction_template_repo_mock, 1, wrong_template_id)

        transaction_template_repo_mock.get_by_id.assert_called_once_with(
            wrong_template_id
        )

    async def test_validate_template_wrong_owner(
            self,
            transaction_template_repo_mock: TransactionTemplateRepository,
            existing_template: TransactionTemplate
    ):
        """
        GIVEN: Transaction template exists but owned by different user
        WHEN: validate_template called with wrong user_id
        THEN: PermissionException raised
        """

        transaction_template_repo_mock.get_by_id.return_value = existing_template

        wrong_user_id = existing_template.user_id + 1

        with pytest.raises(PermissionException, match="You don't have permission to this transaction template"):
            await validate_template(transaction_template_repo_mock, wrong_user_id, existing_template.id)

        transaction_template_repo_mock.get_by_id.assert_called_once_with(
            existing_template.id
        )


class TestValidateBudget:
    async def test_validate_budget_success(
            self,
            budget_repo_mock: BudgetRepository,
            existing_budget: Budget
    ):
        """
        GIVEN: Budget exists, owned by user
        WHEN: validate_budget called
        THEN: Returns the same budget instance
        """

        budget_repo_mock.get_by_id.return_value = existing_budget

        result = await validate_budget(
            budget_repo_mock,
            existing_budget.user_id,
            existing_budget.id
        )

        assert result is existing_budget

        assert_model_fields(
            result,
            id=existing_budget.id,
            name=existing_budget.name,
            amount=existing_budget.amount,
            user_id=existing_budget.user_id,
            currency_code=existing_budget.currency_code,
            category_id=existing_budget.category_id,
        )

        budget_repo_mock.get_by_id.assert_called_once_with(
            existing_budget.id
        )

    async def test_validate_budget_not_found(
            self,
            budget_repo_mock: BudgetRepository,
    ):
        """
        GIVEN: Budget doesn't exist
        WHEN: validate_budget called
        THEN: NotFoundException raised
        """

        budget_repo_mock.get_by_id.return_value = None

        wrong_budget_id = 999

        with pytest.raises(NotFoundException, match="Budget not found"):
            await validate_budget(budget_repo_mock, 1, wrong_budget_id)

        budget_repo_mock.get_by_id.assert_called_once_with(
            wrong_budget_id
        )

    async def test_validate_budget_wrong_owner(
            self,
            budget_repo_mock: BudgetRepository,
            existing_budget: Budget
    ):
        """
        GIVEN: Budget exists but owned by different user
        WHEN: validate_budget called with wrong user_id
        THEN: PermissionException raised
        """

        budget_repo_mock.get_by_id.return_value = existing_budget

        wrong_user_id = existing_budget.user_id + 1

        with pytest.raises(PermissionException, match="You don't have permission to this budget"):
            await validate_budget(budget_repo_mock, wrong_user_id, existing_budget.id)

        budget_repo_mock.get_by_id.assert_called_once_with(
            existing_budget.id
        )


class TestResolveSettledAmount:
    def test_resolve_settled_amount_success(
            self,
            existing_account: Account,
    ):
        """
        GIVEN: Transaction currency matches the account, settled amount not given
        WHEN: resolve_settled_amount called
        THEN: Returns the transaction amount
        """
        expected = Decimal("200.00")

        result = resolve_settled_amount(
            existing_account,
            existing_account.currency_code,
            expected,
            None,
        )

        assert result == expected

    def test_resolve_settled_amount_different_currency_success(
            self,
            existing_account: Account,
            existing_usd_currency: Currency,
    ):
        """
        GIVEN: Transaction currency differs from the account, settled amount given
        WHEN: resolve_settled_amount called
        THEN: Returns the settled amount, not the transaction amount
        """
        expected = Decimal("1050.00")

        result = resolve_settled_amount(
            existing_account,
            existing_usd_currency.code,
            Decimal("20.00"),
            expected,
        )

        assert result == expected

    def test_resolve_settled_amount_same_currency_with_settled_amount(
            self,
            existing_account: Account,
    ):
        """
        GIVEN: Transaction currency matches the account, but settled amount is given
        WHEN: resolve_settled_amount called
        THEN: NotAllowedActionException raised
        """
        with pytest.raises(NotAllowedActionException,
                           match="Amount charged to the account is only needed when currencies differ"):
            resolve_settled_amount(
                existing_account,
                existing_account.currency_code,
                Decimal("200.00"),
                Decimal("1050.00")
            )

    def test_resolve_settled_amount_different_currency_without_settled_amount(
            self,
            existing_account: Account,
            existing_usd_currency: Currency,
    ):
        """
        GIVEN: Transaction currency differs from the account, settled amount not given
        WHEN: resolve_settled_amount called
        THEN: NotAllowedActionException raised
        """
        with pytest.raises(NotAllowedActionException,
                           match="Amount charged to the account is required, in the account currency"):
            resolve_settled_amount(
                existing_account,
                existing_usd_currency.code,
                Decimal("20.00"),
                None
            )
