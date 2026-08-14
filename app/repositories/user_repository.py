from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return (
            await self.session.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        return (
            await self.session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        return (
            await self.session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.commit()

        await self.session.refresh(user)

        return user

    async def add(
            self,
            user: User,
    ) -> User:
        self.session.add(user)

        await self.session.flush()

        return user

    async def update(self, user: User) -> User:
        await self.session.flush()

        return user
