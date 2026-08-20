from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account
from app.schemas import AccountStatus


class AccountRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, account_id: int) -> Account | None:
        return (
            await self.session.execute(select(Account).where(Account.id == account_id))
        ).scalar_one_or_none()

    async def get_by_user(
        self,
        user_id: int,
        status: AccountStatus = AccountStatus.ACTIVE,
    ) -> list[Account]:
        query = select(Account).where(Account.user_id == user_id)

        if status == AccountStatus.ACTIVE:
            query = query.where(Account.archived_at.is_(None))

        elif status == AccountStatus.ARCHIVED:
            query = query.where(Account.archived_at.is_not(None))

        result = await self.session.execute(query)

        return list(result.scalars().all())

    async def get_by_user_and_name(self, user_id: int, name: str) -> Account | None:
        return (
            await self.session.execute(
                select(Account).where(Account.user_id == user_id).where(Account.name == name)
            )
        ).scalar_one_or_none()

    async def update(self, account: Account) -> Account:
        await self.session.flush()

        return account

    async def archive(self, account: Account) -> None:
        account.archived_at = datetime.now(UTC)

        await self.session.flush()

    async def restore(self, account: Account) -> None:
        account.archived_at = None

        await self.session.flush()

    async def add(self, account: Account) -> Account:
        self.session.add(account)

        await self.session.flush()

        return account
