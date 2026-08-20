from decimal import Decimal

from app.core.exceptions import (
    AuthenticationException,
    NotAllowedActionException,
    NotFoundException,
    PermissionException,
)
from app.models import Account, Budget, Category, Currency, Transaction, TransactionTemplate, User
from app.repositories import (
    AccountRepository,
    BudgetRepository,
    CategoryRepository,
    CurrencyRepository,
    TransactionRepository,
    TransactionTemplateRepository,
    UserRepository,
)


async def validate_category(
    category_repository: CategoryRepository,
    user_id: int,
    category_id: int | None,
    allow_archived: bool = False,
) -> Category | None:
    """
    Validate category exists, is owned by user, and not archived.

    Args:
        category_repository: Repository to fetch category
        user_id: User who should own the category
        category_id: Category to validate (None = skip validation)

    Returns:
        Validated Category instance, or None if category_id is None

    Raises:
        NotFoundException: Category doesn't exist
        PermissionException: Category not owned by user
        NotAllowedActionException: Category is archived
    """

    if category_id is None:
        return None

    existing_category = await category_repository.get_by_id(category_id)

    if not existing_category:
        raise NotFoundException("Category not found")

    if existing_category.user_id != user_id:
        raise PermissionException("You don't have permission to this category")

    if not allow_archived and existing_category.archived_at:
        raise NotAllowedActionException("Archived category is not allowed to use")

    return existing_category


async def validate_currency(
    currency_repository: CurrencyRepository,
    currency_code: str,
    allow_inactive: bool = False,
) -> Currency:
    """
    Validate currency exists and is active.

    Args:
        currency_repository: Repository to fetch currency
        currency_code: Currency code to validate

    Returns:
        Validated Currency instance

    Raises:
        NotFoundException: Currency doesn't exist
        NotAllowedActionException: Currency is inactive
    """

    existing_currency = await currency_repository.get_by_code(currency_code)

    if not existing_currency:
        raise NotFoundException("Currency not found")

    if not allow_inactive and not existing_currency.is_active:
        raise NotAllowedActionException("Currency is not active")

    return existing_currency


async def validate_transaction(
    transaction_repository: TransactionRepository, user_id: int, transaction_id: int
) -> Transaction:
    """
    Validate transaction exists and is owned by user.

    Args:
        transaction_repository: Repository to fetch transaction
        user_id: User who should own the transaction
        transaction_id: Transaction to validate

    Returns:
        Validated Transaction instance

    Raises:
        NotFoundException: Transaction doesn't exist
        PermissionException: Transaction not owned by user
    """

    existing_transaction = await transaction_repository.get_by_id(transaction_id)

    if not existing_transaction:
        raise NotFoundException("Transaction not found")

    if existing_transaction.user_id != user_id:
        raise PermissionException("You don't have permission to this transaction")

    return existing_transaction


async def validate_template(
    transaction_template_repository: TransactionTemplateRepository,
    user_id: int,
    transaction_template_id: int,
) -> TransactionTemplate:
    """
    Validate transaction template exists and is owned by user.

    Args:
        transaction_template_repository: Repository to fetch template
        user_id: User who should own the template
        transaction_template_id: Template to validate

    Returns:
        Validated TransactionTemplate instance

    Raises:
        NotFoundException: Template doesn't exist
        PermissionException: Template not owned by user
    """

    existing_transaction_template = await transaction_template_repository.get_by_id(
        transaction_template_id
    )

    if not existing_transaction_template:
        raise NotFoundException("Transaction template not found")

    if existing_transaction_template.user_id != user_id:
        raise PermissionException("You don't have permission to this transaction template")

    return existing_transaction_template


async def validate_budget(
    budget_repository: BudgetRepository, user_id: int, budget_id: int
) -> Budget:
    """
    Validate budget exists and is owned by user.

    Args:
        budget_repository: Repository to fetch budget
        user_id: User who should own the budget
        budget_id: Budget to validate

    Returns:
        Validated Budget instance

    Raises:
        NotFoundException: Budget doesn't exist
        PermissionException: Budget not owned by user
    """

    existing_budget = await budget_repository.get_by_id(budget_id)

    if not existing_budget:
        raise NotFoundException("Budget not found")

    if existing_budget.user_id != user_id:
        raise PermissionException("You don't have permission to this budget")

    return existing_budget


async def validate_user(
    user_repository: UserRepository,
    user_id: int,
) -> User:
    """
    Validate that the user from the token still exists.

    Args:
        user_repository: Repository to fetch user
        user_id: User id taken from the JWT token

    Returns:
        Validated User instance

    Raises:
        AuthenticationException: User no longer exists. 401, not 404 —
            the token is valid but points to a deleted user, so the
            correct action is to re-login, not "resource not found".
    """
    user = await user_repository.get_by_id(user_id)
    if user is None:
        raise AuthenticationException("User no longer exists")
    return user


async def validate_account(
    account_repository: AccountRepository,
    user_id: int,
    account_id: int,
    allow_archived: bool = False,
) -> Account:
    """
    Validate account exists, is owned by user, and (optionally) not archived.

    Args:
        account_repository: Repository to fetch account
        user_id: User who should own the account
        account_id: Account to validate
        allow_archived: Skip the archived check. Editing an existing
            transaction must stay possible even if its account was
            archived later; only attaching a transaction TO an archived
            account is forbidden.

    Returns:
        Validated Account instance

    Raises:
        NotFoundException: Account doesn't exist
        PermissionException: Account not owned by user
        NotAllowedActionException: Account is archived and allow_archived is False
    """
    existing_account = await account_repository.get_by_id(account_id)

    if not existing_account:
        raise NotFoundException("Account not found")

    if existing_account.user_id != user_id:
        raise PermissionException("You don't have permission to this account")

    if not allow_archived and existing_account.archived_at:
        raise NotAllowedActionException("Archived account is not allowed to use")

    return existing_account


def resolve_settled_amount(
    account: Account,
    currency_code: str,
    amount: Decimal,
    settled_amount: Decimal | None,
) -> Decimal:
    """
    Resolve how much was moved on the account, in the account currency.

    Same currency: settled equals amount, nothing to state.
    Different currency: the caller must say what the account was charged —
        the system has no exchange rates to work it out.

    Returns:
        Amount in the account currency

    Raises:
        NotAllowedActionException: Settled amount is missing or redundant
    """
    if account.currency_code == currency_code:
        if settled_amount is not None:
            raise NotAllowedActionException(
                "Amount charged to the account is only needed when currencies differ"
            )
        return amount

    if settled_amount is None:
        raise NotAllowedActionException(
            "Amount charged to the account is required, in the account currency"
        )

    return settled_amount
