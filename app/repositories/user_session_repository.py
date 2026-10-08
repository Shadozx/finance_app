import uuid
from datetime import datetime
from typing import cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SessionRevocationReason, User, UserSession


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

    async def get_active_by_user(
        self, user_id: int, now: datetime, limit: int, offset: int
    ) -> list[UserSession]:
        query = (
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .where(UserSession.revoked_at.is_(None))
            .where(UserSession.expires_at > now)
            .order_by(UserSession.last_used_at.desc(), UserSession.id.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(query)

        return list(result.scalars().all())

    async def get_by_id_for_update(self, session_id: uuid.UUID) -> UserSession | None:
        # Locks last until the service commits or request cleanup rolls back the transaction.
        return (
            await self.session.execute(
                select(UserSession)
                .where(UserSession.id == session_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    async def add(
        self,
        user_session: UserSession,
    ) -> UserSession:
        self.session.add(user_session)

        await self.session.flush()

        return user_session

    async def update(self, user_session: UserSession) -> UserSession:
        await self.session.flush()

        return user_session

    async def revoke_active_except(
        self,
        user_id: int,
        *,
        keep_session_id: uuid.UUID,
        now: datetime,
        reason: SessionRevocationReason,
    ) -> int:
        query = (
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .where(UserSession.revoked_at.is_(None))
            .where(UserSession.expires_at > now)
            .where(UserSession.id != keep_session_id)
            .values(revoked_at=now, revoked_reason=reason)
        )

        result = cast(CursorResult, await self.session.execute(query))

        return result.rowcount

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
