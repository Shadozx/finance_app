import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from structlog.testing import capture_logs

from app.core import UnitOfWork
from app.core.exceptions import NotFoundException
from app.models import SessionRevocationReason, User, UserSession
from app.repositories import UserSessionRepository
from app.services import UserSessionService
from app.services.user_session_service import SESSION_NOT_FOUND_MESSAGE

SESSION_TIME_OFFSET = timedelta(days=1)


def revoke(session: UserSession, now: datetime) -> None:
    session.revoked_at = now - SESSION_TIME_OFFSET
    session.revoked_reason = SessionRevocationReason.REUSE_DETECTED


def expire(session: UserSession, now: datetime) -> None:
    session.expires_at = now - SESSION_TIME_OFFSET


def expire_now(session: UserSession, now: datetime) -> None:
    session.expires_at = now


def keep_active(session: UserSession, now: datetime) -> None:
    pass


class TestGetUserSessions:
    @pytest.fixture
    def session_rows(self, active_user_session: UserSession):
        other_session_count = 2
        other_sessions = [
            UserSession(
                id=uuid.uuid4(),
                user_id=active_user_session.user_id,
                user_agent="Other browser",
                refresh_token_hash=active_user_session.refresh_token_hash,
                created_at=active_user_session.created_at,
                last_used_at=active_user_session.last_used_at,
                expires_at=active_user_session.expires_at,
            )
            for _ in range(other_session_count)
        ]
        return [*other_sessions, active_user_session]

    @pytest.mark.parametrize(
        "user_agent",
        [
            pytest.param(None, id="without_user_agent"),
            pytest.param("Current browser", id="with_user_agent"),
        ],
    )
    async def test_get_user_sessions_returns_public_fields_with_current_flag(
        self,
        user_session_service: UserSessionService,
        user_session_repo_mock: UserSessionRepository,
        active_user_session: UserSession,
        session_rows: list[UserSession],
        session_now: datetime,
        user_agent: str | None,
    ):
        active_user_session.user_agent = user_agent
        user_session_repo_mock.get_active_by_user.return_value = session_rows
        limit = len(session_rows)
        offset = 0

        result = await user_session_service.get_user_sessions(
            active_user_session.user_id, active_user_session.id, limit=limit, offset=offset
        )

        assert [item.is_current for item in result.items] == [False, False, True]
        for item, user_session in zip(result.items, session_rows, strict=True):
            assert item.model_dump() == {
                "id": user_session.id,
                "user_agent": user_session.user_agent,
                "created_at": user_session.created_at,
                "last_used_at": user_session.last_used_at,
                "is_current": user_session is active_user_session,
            }
        assert result.limit == limit
        assert result.offset == offset
        assert result.has_more is False
        user_session_repo_mock.get_active_by_user.assert_awaited_once_with(
            active_user_session.user_id, session_now, limit + 1, offset
        )

    async def test_get_user_sessions_extra_row_returns_has_more(
        self,
        user_session_service: UserSessionService,
        user_session_repo_mock: UserSessionRepository,
        active_user_session: UserSession,
        session_rows: list[UserSession],
        session_now: datetime,
    ):
        limit = len(session_rows) - 1
        offset = limit
        user_session_repo_mock.get_active_by_user.return_value = session_rows

        result = await user_session_service.get_user_sessions(
            active_user_session.user_id, active_user_session.id, limit=limit, offset=offset
        )

        expected_session_ids = [user_session.id for user_session in session_rows[:limit]]

        assert result.has_more is True
        assert len(result.items) == limit
        assert [item.id for item in result.items] == expected_session_ids
        assert all(item.is_current is False for item in result.items)
        assert result.limit == limit
        assert result.offset == offset
        user_session_repo_mock.get_active_by_user.assert_awaited_once_with(
            active_user_session.user_id, session_now, limit + 1, offset
        )

    @pytest.mark.parametrize(
        "row_count",
        [
            pytest.param(0, id="empty"),
            pytest.param(1, id="short"),
            pytest.param(2, id="full"),
        ],
    )
    async def test_get_user_sessions_last_page_returns_no_more(
        self,
        user_session_service: UserSessionService,
        user_session_repo_mock: UserSessionRepository,
        active_user_session: UserSession,
        session_rows: list[UserSession],
        session_now: datetime,
        row_count: int,
    ):
        limit = len(session_rows) - 1
        offset = limit
        rows = session_rows[:row_count]
        user_session_repo_mock.get_active_by_user.return_value = rows

        result = await user_session_service.get_user_sessions(
            active_user_session.user_id, active_user_session.id, limit=limit, offset=offset
        )

        expected_session_ids = [user_session.id for user_session in rows]

        assert result.has_more is False
        assert [item.id for item in result.items] == expected_session_ids
        assert result.limit == limit
        assert result.offset == offset
        user_session_repo_mock.get_active_by_user.assert_awaited_once_with(
            active_user_session.user_id, session_now, limit + 1, offset
        )


class TestRevokeSession:
    async def test_revoke_session_own_active_session_sets_revoked_at(
        self,
        user_session_service: UserSessionService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        active_user_session: UserSession,
        session_now: datetime,
    ):
        user_session_repo_mock.get_by_id_for_update.return_value = active_user_session

        async def commit_revocation():
            user_session_repo_mock.update.assert_awaited_once_with(active_user_session)
            assert active_user_session.revoked_at == session_now
            assert active_user_session.revoked_reason == SessionRevocationReason.REVOKED_BY_USER
            assert logs == []

        unit_of_work_mock.commit.side_effect = commit_revocation

        with capture_logs() as logs:
            result = await user_session_service.revoke_session(
                active_user_session.user_id, active_user_session.id
            )

        assert result is None
        assert active_user_session.revoked_at == session_now
        assert active_user_session.revoked_reason == SessionRevocationReason.REVOKED_BY_USER
        user_session_repo_mock.get_by_id_for_update.assert_awaited_once_with(active_user_session.id)
        user_session_repo_mock.update.assert_awaited_once_with(active_user_session)
        unit_of_work_mock.commit.assert_awaited_once()
        assert logs == [
            {
                "event": "user_session_revoked",
                "user_id": active_user_session.user_id,
                "session_id": str(active_user_session.id),
                "log_level": "info",
            }
        ]

    async def test_revoke_session_unknown_id_raises_not_found(
        self,
        user_session_service: UserSessionService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        active_user_session: UserSession,
    ):
        user_session_repo_mock.get_by_id_for_update.return_value = None
        original_revoked_at = active_user_session.revoked_at
        original_reason = active_user_session.revoked_reason

        with capture_logs() as logs:
            with pytest.raises(NotFoundException) as exc_info:
                await user_session_service.revoke_session(existing_user.id, active_user_session.id)

        assert exc_info.value.message == SESSION_NOT_FOUND_MESSAGE
        assert exc_info.value.errors == []
        assert active_user_session.revoked_at == original_revoked_at
        assert active_user_session.revoked_reason == original_reason
        user_session_repo_mock.get_by_id_for_update.assert_awaited_once_with(active_user_session.id)
        user_session_repo_mock.update.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()
        assert logs == []

    @pytest.mark.parametrize(
        "make_state",
        [
            pytest.param(revoke, id="revoked"),
            pytest.param(expire, id="expired"),
            pytest.param(expire_now, id="expiring_now"),
        ],
    )
    async def test_revoke_session_unavailable_own_session_raises_not_found(
        self,
        user_session_service: UserSessionService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        active_user_session: UserSession,
        session_now: datetime,
        make_state: Callable[[UserSession, datetime], None],
    ):
        make_state(active_user_session, session_now)
        user_session_repo_mock.get_by_id_for_update.return_value = active_user_session
        original_revoked_at = active_user_session.revoked_at
        original_reason = active_user_session.revoked_reason

        with capture_logs() as logs:
            with pytest.raises(NotFoundException) as exc_info:
                await user_session_service.revoke_session(existing_user.id, active_user_session.id)

        assert exc_info.value.message == SESSION_NOT_FOUND_MESSAGE
        assert exc_info.value.errors == []
        assert active_user_session.revoked_at == original_revoked_at
        assert active_user_session.revoked_reason == original_reason
        user_session_repo_mock.get_by_id_for_update.assert_awaited_once_with(active_user_session.id)
        user_session_repo_mock.update.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()
        assert logs == []

    @pytest.mark.parametrize(
        "make_state",
        [
            pytest.param(keep_active, id="active"),
            pytest.param(revoke, id="revoked"),
            pytest.param(expire, id="expired"),
            pytest.param(expire_now, id="expiring_now"),
        ],
    )
    async def test_revoke_session_other_users_session_raises_not_found(
        self,
        user_session_service: UserSessionService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        existing_user: User,
        active_user_session: UserSession,
        session_now: datetime,
        make_state: Callable[[UserSession, datetime], None],
    ):
        other_user_id = existing_user.id + 1
        active_user_session.user_id = other_user_id
        make_state(active_user_session, session_now)
        user_session_repo_mock.get_by_id_for_update.return_value = active_user_session
        original_revoked_at = active_user_session.revoked_at
        original_reason = active_user_session.revoked_reason

        with capture_logs() as logs:
            with pytest.raises(NotFoundException) as exc_info:
                await user_session_service.revoke_session(existing_user.id, active_user_session.id)

        assert exc_info.value.message == SESSION_NOT_FOUND_MESSAGE
        assert exc_info.value.errors == []
        assert active_user_session.revoked_at == original_revoked_at
        assert active_user_session.revoked_reason == original_reason
        user_session_repo_mock.get_by_id_for_update.assert_awaited_once_with(active_user_session.id)
        user_session_repo_mock.update.assert_not_awaited()
        unit_of_work_mock.commit.assert_not_awaited()
        assert logs == [
            {
                "event": "user_session_permission_denied",
                "user_id": existing_user.id,
                "session_id": str(active_user_session.id),
                "log_level": "warning",
            }
        ]


class TestRevokeOtherSessions:
    @pytest.mark.parametrize(
        "revoked_count",
        [
            pytest.param(0, id="none_revoked"),
            pytest.param(2, id="some_revoked"),
        ],
    )
    async def test_revoke_other_sessions_revokes_all_except_current(
        self,
        user_session_service: UserSessionService,
        user_session_repo_mock: UserSessionRepository,
        unit_of_work_mock: UnitOfWork,
        active_user_session: UserSession,
        session_now: datetime,
        revoked_count: int,
    ):
        user_session_repo_mock.revoke_active_except.return_value = revoked_count

        async def commit_revocation():
            user_session_repo_mock.revoke_active_except.assert_awaited_once_with(
                active_user_session.user_id,
                keep_session_id=active_user_session.id,
                now=session_now,
                reason=SessionRevocationReason.REVOKED_BY_USER,
            )
            assert logs == []

        unit_of_work_mock.commit.side_effect = commit_revocation

        with capture_logs() as logs:
            result = await user_session_service.revoke_other_sessions(
                active_user_session.user_id, active_user_session.id
            )

        assert result is None
        unit_of_work_mock.commit.assert_awaited_once()
        assert logs == [
            {
                "event": "user_sessions_revoked",
                "user_id": active_user_session.user_id,
                "revoked_count": revoked_count,
                "log_level": "info",
            }
        ]
