import structlog

from decimal import Decimal
from uuid import UUID, uuid4

from app.core import UnitOfWork
from app.models import Account, Transaction, TransactionKind, TransactionType
from app.repositories import AccountRepository, TransactionRepository, CurrencyRepository
from app.schemas import TransferCreate, TransferUpdate, TransferResponse
from app.core.exceptions import NotFoundException, NotAllowedActionException
from app.services import validators

logger = structlog.get_logger()


class TransferService:

    def __init__(
            self,
            transaction_repository: TransactionRepository,
            account_repository: AccountRepository,
            currency_repository: CurrencyRepository,
            unit_of_work: UnitOfWork
    ):
        self.transaction_repository = transaction_repository
        self.account_repository = account_repository
        self.currency_repository = currency_repository
        self.unit_of_work = unit_of_work


    async def create_transfer(
            self,
            data: TransferCreate,
            user_id: int,
    ) -> TransferResponse:
        from_account = await validators.validate_account(
            self.account_repository, user_id, data.from_account_id
        )

        to_account = await validators.validate_account(
            self.account_repository, user_id, data.to_account_id
        )

        await validators.validate_currency(self.currency_repository, from_account.currency_code)
        await validators.validate_currency(self.currency_repository, to_account.currency_code)

        self._validate_amounts(data, from_account, to_account)

        transfer_group_id = uuid4()

        from_side = Transaction(
            type=TransactionType.EXPENSE,
            kind=TransactionKind.TRANSFER,
            amount=data.from_amount,
            description=data.description,
            currency_code=from_account.currency_code,
            settled_amount=data.from_amount,
            settled_currency_code=from_account.currency_code,
            account_id=from_account.id,
            user_id=user_id,
            category_id=None,
            transfer_group_id=transfer_group_id,
            date=data.date,
        )

        to_side = Transaction(
            type=TransactionType.INCOME,
            kind=TransactionKind.TRANSFER,
            amount=data.to_amount,
            description=data.description,
            currency_code=to_account.currency_code,
            settled_amount=data.to_amount,
            settled_currency_code=to_account.currency_code,
            account_id=to_account.id,
            user_id=user_id,
            category_id=None,
            transfer_group_id=transfer_group_id,
            date=data.date,
        )

        await self.transaction_repository.add(from_side)
        await self.transaction_repository.add(to_side)
        await self.transaction_repository.commit()

        logger.info(
            "transfer_create_success",
            user_id=user_id,
            transfer_group_id=str(transfer_group_id),
        )

        return self._to_response(transfer_group_id, from_side, to_side, from_account, to_account)

    async def get_transfer(
            self,
            transfer_group_id: UUID,
            user_id: int,
    ) -> TransferResponse:
        from_side, to_side = await self._get_sides(transfer_group_id, user_id)

        from_account = await validators.validate_account(
            self.account_repository, user_id, from_side.account_id, allow_archived=True
        )

        to_account = await validators.validate_account(
            self.account_repository, user_id, to_side.account_id, allow_archived=True
        )

        return self._to_response(transfer_group_id, from_side, to_side, from_account, to_account)

    async def update_transfer(
            self,
            transfer_group_id: UUID,
            data: TransferUpdate,
            user_id: int,
    ) -> TransferResponse:
        from_side, to_side = await self._get_sides(transfer_group_id, user_id)

        current_account_ids = {from_side.account_id, to_side.account_id}

        from_account = await validators.validate_account(
            self.account_repository,
            user_id,
            data.from_account_id,
            allow_archived=data.from_account_id in current_account_ids,
        )

        to_account = await validators.validate_account(
            self.account_repository,
            user_id,
            data.to_account_id,
            allow_archived=data.to_account_id in current_account_ids,
        )

        await validators.validate_currency(
            self.currency_repository,
            from_account.currency_code,
            allow_inactive=data.from_account_id in current_account_ids,
        )

        await validators.validate_currency(
            self.currency_repository,
            to_account.currency_code,
            allow_inactive=data.to_account_id in current_account_ids,
        )

        self._validate_amounts(data, from_account, to_account)

        self._write_side(from_side, TransactionType.EXPENSE, from_account, data.from_amount, data)
        self._write_side(to_side, TransactionType.INCOME, to_account, data.to_amount, data)

        await self.transaction_repository.commit()

        logger.info(
            "transfer_update_success",
            user_id=user_id,
            transfer_group_id=str(transfer_group_id),
        )

        return self._to_response(transfer_group_id, from_side, to_side, from_account, to_account)

    async def delete_transfer(
            self,
            transfer_group_id: UUID,
            user_id: int,
    ) -> None:
        await self._get_sides(transfer_group_id, user_id)

        await self.transaction_repository.delete_by_transfer_group(transfer_group_id, user_id)

        logger.info(
            "transfer_delete_success",
            user_id=user_id,
            transfer_group_id=str(transfer_group_id),
        )

    async def _get_sides(
            self,
            transfer_group_id: UUID,
            user_id: int,
    ) -> tuple[Transaction, Transaction]:
        """Load both sides of a transfer.

        A group must hold exactly one EXPENSE and one INCOME. Anything else
        (a leftover single row, a duplicated direction) is not a transfer that
        can be shown or edited as a whole — the remaining row stays visible in
        the register and can be removed through DELETE /transactions/{id}.
        """
        sides = await self.transaction_repository.get_by_transfer_group(transfer_group_id, user_id)

        from_side = next((side for side in sides if side.type == TransactionType.EXPENSE), None)
        to_side = next((side for side in sides if side.type == TransactionType.INCOME), None)

        if len(sides) != 2 or from_side is None or to_side is None:
            raise NotFoundException("Transfer not found")

        return from_side, to_side

    @staticmethod
    def _validate_amounts(
            data: TransferCreate,
            from_account: Account,
            to_account: Account,
    ) -> None:
        if from_account.currency_code != to_account.currency_code:
            return

        if data.from_amount != data.to_amount:
            raise NotAllowedActionException(
                "Transfer between accounts in the same currency must have equal amounts"
            )

    @staticmethod
    def _write_side(
            side: Transaction,
            transaction_type: TransactionType,
            account: Account,
            amount: Decimal,
            data: TransferUpdate,
    ) -> None:
        side.type = transaction_type
        side.amount = amount
        side.account_id = account.id
        side.currency_code = account.currency_code
        side.settled_amount = amount
        side.settled_currency_code = account.currency_code
        side.description = data.description
        side.date = data.date

    def _to_response(
            self,
            transfer_group_id: UUID,
            from_side: Transaction,
            to_side: Transaction,
            from_account: Account,
            to_account: Account,
    ) -> TransferResponse:
        return TransferResponse(
            transfer_group_id=transfer_group_id,
            from_account_id=from_account.id,
            from_account_name=from_account.name,
            from_currency_code=from_account.currency_code,
            from_amount=from_side.amount,
            to_account_id=to_account.id,
            to_account_name=to_account.name,
            to_currency_code=to_account.currency_code,
            to_amount=to_side.amount,
            exchange_rate=self._exchange_rate(from_side, to_side),
            description=from_side.description,
            date=from_side.date,
        )

    @staticmethod
    def _exchange_rate(from_side: Transaction, to_side: Transaction) -> Decimal | None:
        """Rate implied by the two settled amounts, each in its account currency."""
        if from_side.currency_code == to_side.currency_code:
            return None

        return from_side.settled_amount / to_side.settled_amount