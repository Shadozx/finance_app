import structlog

from app.models import Account
from app.repositories import AccountRepository, CurrencyRepository
from app.schemas import AccountCreate, AccountUpdate, AccountResponse, AccountStatus
from app.core.exceptions import ValueExistsException, NotAllowedActionException
from app.services import validators

logger = structlog.get_logger()


class AccountService:

    def __init__(self,
                 account_repository: AccountRepository,
                 currency_repository: CurrencyRepository,
                 ):
        self.account_repository = account_repository
        self.currency_repository = currency_repository

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

        created_account = await self.account_repository.create(new_account)

        logger.info("account_create_success", user_id=user_id, account_id=created_account.id)

        return AccountResponse.model_validate(created_account)

    async def get_account(
            self,
            account_id: int,
            user_id: int
    ) -> AccountResponse:
        account = await validators.validate_account(
            self.account_repository,
            user_id,
            account_id,
            allow_archived=True,
        )

        return AccountResponse.model_validate(account)

    async def get_user_accounts(
            self,
            user_id: int,
            status: AccountStatus = AccountStatus.ACTIVE,
    ) -> list[AccountResponse]:
        accounts = await self.account_repository.get_by_user(
            user_id=user_id,
            status=status,
        )

        return [AccountResponse.model_validate(account) for account in accounts]

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

        logger.info("account_update_success", user_id=user_id, account_id=updated_account.id)

        return AccountResponse.model_validate(updated_account)

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

        logger.info("account_restore_success", user_id=user_id, account_id=existing_account.id)

        return AccountResponse.model_validate(existing_account)
