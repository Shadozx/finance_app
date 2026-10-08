from uuid import UUID

import structlog

from app.core import UnitOfWork, utc_now
from app.core.exceptions import NotFoundException
from app.models import SessionRevocationReason, UserSession
from app.repositories import UserSessionRepository
from app.schemas import Page, UserSessionResponse

logger = structlog.get_logger()

SESSION_NOT_FOUND_MESSAGE = "Session not found"


class UserSessionService:
    def __init__(
        self,
        user_session_repository: UserSessionRepository,
        unit_of_work: UnitOfWork,
    ):
        self.user_session_repository = user_session_repository
        self.unit_of_work = unit_of_work

    async def list_sessions(
        self,
        user_id: int,
        current_session_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> Page[UserSessionResponse]:
        now = utc_now()
        rows = await self.user_session_repository.get_active_by_user(
            user_id, now, limit + 1, offset
        )

        has_more = len(rows) > limit

        return Page(
            items=[
                self._to_response(user_session, current_session_id) for user_session in rows[:limit]
            ],
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    async def revoke_session(self, user_id: int, session_id: UUID) -> None:
        user_session = await self.user_session_repository.get_by_id_for_update(session_id)

        if user_session is None:
            raise NotFoundException(SESSION_NOT_FOUND_MESSAGE)

        if user_session.user_id != user_id:
            logger.warning(
                "user_session_permission_denied", user_id=user_id, session_id=str(session_id)
            )

            raise NotFoundException(SESSION_NOT_FOUND_MESSAGE)

        now = utc_now()

        if user_session.revoked_at is not None or user_session.expires_at <= now:
            raise NotFoundException(SESSION_NOT_FOUND_MESSAGE)

        user_session.revoked_at = now
        user_session.revoked_reason = SessionRevocationReason.REVOKED_BY_USER

        await self.user_session_repository.update(user_session)
        await self.unit_of_work.commit()

        logger.info("user_session_revoked", user_id=user_id, session_id=str(session_id))

    async def revoke_other_sessions(self, user_id: int, current_session_id: UUID) -> None:
        count = await self.user_session_repository.revoke_active_except(
            user_id,
            keep_session_id=current_session_id,
            now=utc_now(),
            reason=SessionRevocationReason.REVOKED_BY_USER,
        )

        await self.unit_of_work.commit()

        logger.info("user_sessions_revoked", user_id=user_id, revoked_count=count)

    def _to_response(
        self, user_session: UserSession, current_session_id: UUID
    ) -> UserSessionResponse:
        return UserSessionResponse(
            id=user_session.id,
            user_agent=user_session.user_agent,
            created_at=user_session.created_at,
            last_used_at=user_session.last_used_at,
            is_current=user_session.id == current_session_id,
        )
