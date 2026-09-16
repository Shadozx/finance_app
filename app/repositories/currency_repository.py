from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Currency


class CurrencyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_code(self, code: str) -> Currency | None:
        return (
            await self.session.execute(select(Currency).where(Currency.code == code))
        ).scalar_one_or_none()

    async def get_active(self, limit: int = 200, offset: int = 0) -> list[Currency]:
        return cast(
            list[Currency],
            (
                await self.session.execute(
                    select(Currency)
                    .where(Currency.is_active.is_(True))
                    .order_by(Currency.code)
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all(),
        )
