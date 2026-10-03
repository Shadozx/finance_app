import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserSession


class UserSessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_with_user(
        self, session_id: uuid.UUID, now: datetime
    ) -> tuple[UserSession, User] | None:
        return (
            (
                await self.session.execute(
                    select(UserSession, User)
                    .join(User, User.id == UserSession.user_id)
                    .where(UserSession.id == session_id)
                    .where(UserSession.revoked_at.is_(None))
                    .where(UserSession.expires_at > now)
                )
            )
            .tuples()
            .one_or_none()
        )

    async def add(
        self,
        user_session: UserSession,
    ) -> UserSession:
        self.session.add(user_session)

        await self.session.flush()

        return user_session

    async def delete_expired_sessions(
        self,
        user_id: int,
        now: datetime,
    ) -> None:
        query = (
            delete(UserSession)
            .where(UserSession.user_id == user_id)
            .where(UserSession.expires_at < now)
        )

        await self.session.execute(query)
