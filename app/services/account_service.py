from datetime import date
from decimal import Decimal

import structlog

from app.core import UnitOfWork
from app.core.exceptions import NotAllowedActionException, ValueExistsException
from app.models import Account, Transaction, TransactionKind, TransactionType
from app.repositories import AccountRepository, CurrencyRepository, TransactionRepository
from app.schemas import (
    AccountCreate,
    AccountReconcile,
    AccountReconcileResponse,
    AccountResponse,
    AccountStatus,
    AccountUpdate,
    InitialBalanceKind,
)
from app.services import validators

logger = structlog.get_logger()


class AccountService:
    def __init__(
        self,
        account_repository: AccountRepository,
        transaction_repository: TransactionRepository,
        currency_repository: CurrencyRepository,
        unit_of_work: UnitOfWork,
    ):
        self.account_repository = account_repository
        self.transaction_repository = transaction_repository
        self.currency_repository = currency_repository
        self.unit_of_work = unit_of_work

    async def create_account(
        self,
        data: AccountCreate,
        user_id: int,
    ) -> AccountResponse:
        if await self.account_repository.get_by_user_and_name(user_id, data.name):
            raise ValueExistsException("Account with this name exists")

        await validators.validate_currency(self.currency_repository, data.currency_code)

        new_account = Account(
            name=data.name,
            currency_code=data.currency_code,
            user_id=user_id,
        )

        created_account = await self.account_repository.add(new_account)

        initial_balance = data.initial_balance if data.initial_balance != 0 else Decimal("0")

        if initial_balance != 0:
            adjustment = Transaction(
                account_id=created_account.id,
                kind=TransactionKind.ADJUSTMENT
                if data.initial_balance_kind == InitialBalanceKind.EXISTING
                else TransactionKind.REGULAR,
                type=TransactionType.EXPENSE if initial_balance < 0 else TransactionType.INCOME,
                amount=abs(initial_balance),
                settled_amount=abs(initial_balance),
                settled_currency_code=data.currency_code,
                currency_code=data.currency_code,
                user_id=user_id,
                date=date.today(),
            )
            await self.transaction_repository.add(adjustment)

        await self.unit_of_work.commit()

        logger.info("account_create_success", user_id=user_id, account_id=created_account.id)

        return self._to_response(created_account, initial_balance)

    async def get_account(self, account_id: int, user_id: int) -> AccountResponse:
        existing_account = await validators.validate_account(
            self.account_repository,
            user_id,
            account_id,
            allow_archived=True,
        )

        balance = await self.transaction_repository.get_balance(account_id)

        return self._to_response(existing_account, balance)

    async def get_user_accounts(
        self,
        user_id: int,
        status: AccountStatus = AccountStatus.ACTIVE,
    ) -> list[AccountResponse]:
        accounts = await self.account_repository.get_by_user(
            user_id=user_id,
            status=status,
        )

        balances = await self.transaction_repository.get_balances_by_account(user_id)

        return [
            self._to_response(account, balance=balances.get(account.id, Decimal("0")))
            for account in accounts
        ]

    async def update_account(
        self,
        account_id: int,
        data: AccountUpdate,
        user_id: int,
    ) -> AccountResponse:
        existing_account = await validators.validate_account(
            self.account_repository,
            user_id,
            account_id,
            allow_archived=True,
        )

        duplicate = await self.account_repository.get_by_user_and_name(user_id, data.name)

        if duplicate and duplicate.id != account_id:
            raise ValueExistsException("Account with this name exists")

        existing_account.name = data.name

        updated_account = await self.account_repository.update(existing_account)

        await self.unit_of_work.commit()

        logger.info("account_update_success", user_id=user_id, account_id=updated_account.id)

        balance = await self.transaction_repository.get_balance(account_id)

        return self._to_response(updated_account, balance)

    async def reconcile_account(
        self,
        account_id: int,
        data: AccountReconcile,
        user_id: int,
    ) -> AccountReconcileResponse:
        existing_account = await validators.validate_account(
            self.account_repository,
            user_id,
            account_id,
        )

        current_balance = await self.transaction_repository.get_balance(account_id)

        difference = data.actual_balance - current_balance

        if difference == 0:
            logger.info(
                "account_reconcile_no_change",
                user_id=user_id,
                account_id=account_id,
            )

            return AccountReconcileResponse(
                account=self._to_response(existing_account, current_balance),
                difference=Decimal("0"),
                adjusted=False,
            )

        adjustment = Transaction(
            type=TransactionType.INCOME if difference > 0 else TransactionType.EXPENSE,
            kind=TransactionKind.ADJUSTMENT,
            amount=abs(difference),
            description="Balance reconciliation",
            currency_code=existing_account.currency_code,
            settled_amount=abs(difference),
            settled_currency_code=existing_account.currency_code,
            user_id=user_id,
            category_id=None,
            account_id=account_id,
            date=date.today(),
        )

        await self.transaction_repository.add(adjustment)

        await self.unit_of_work.commit()

        logger.info(
            "account_reconcile_success",
            user_id=user_id,
            account_id=account_id,
            difference=str(difference),
        )

        return AccountReconcileResponse(
            account=self._to_response(existing_account, data.actual_balance),
            difference=difference,
            adjusted=True,
        )

    async def archive_account(
        self,
        account_id: int,
        user_id: int,
    ) -> None:
        existing_account = await validators.validate_account(
            self.account_repository,
            user_id,
            account_id,
            allow_archived=True,
        )

        if existing_account.archived_at:
            raise NotAllowedActionException("Account is archived")

        await self.account_repository.archive(existing_account)

        await self.unit_of_work.commit()

        logger.info("account_archive_success", user_id=user_id, account_id=existing_account.id)

    async def restore_account(
        self,
        account_id: int,
        user_id: int,
    ) -> AccountResponse:
        existing_account = await validators.validate_account(
            self.account_repository,
            user_id,
            account_id,
            allow_archived=True,
        )

        if not existing_account.archived_at:
            raise NotAllowedActionException("Account is not archived")

        duplicate = await self.account_repository.get_by_user_and_name(
            user_id,
            existing_account.name,
        )

        if duplicate and duplicate.id != account_id and duplicate.archived_at is None:
            raise ValueExistsException("Active account with this name already exists")

        await self.account_repository.restore(existing_account)

        await self.unit_of_work.commit()

        logger.info("account_restore_success", user_id=user_id, account_id=existing_account.id)

        balance = await self.transaction_repository.get_balance(account_id)

        return self._to_response(existing_account, balance)

    def _to_response(self, account: Account, balance: Decimal) -> AccountResponse:
        return AccountResponse(
            id=account.id,
            name=account.name,
            currency_code=account.currency_code,
            balance=balance,
            archived_at=account.archived_at,
            created_at=account.created_at,
            user_id=account.user_id,
        )
