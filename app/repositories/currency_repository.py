from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Currency


class CurrencyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_code(self, code: str) -> Currency | None:
        return (
            await self.session.execute(
                select(Currency)
                .where(Currency.code == code)
            )
        ).scalar_one_or_none()

    async def get_all_active(self) -> list[Currency]:
        return cast(list[Currency], (
            await self.session.execute(
                select(Currency)
                .where(Currency.is_active == True)
            )
        ).scalars().all())
