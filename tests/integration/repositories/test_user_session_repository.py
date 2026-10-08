import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import utc_now
from app.core.security import hash_refresh_secret
from app.models import SessionRevocationReason, User, UserSession
from app.repositories import UserRepository, UserSessionRepository

SESSION_TIME_OFFSET = timedelta(days=1)
REFRESH_TOKEN_HASH = hash_refresh_secret("repository-refresh-secret")


class TestAdd:
    async def test_add_user_session(
        self,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        user_session = UserSession(
            user_id=user.id,
            expires_at=now + SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )

        created_session = await user_session_repository.add(user_session)

        assert created_session.id is not None


class TestUpdate:
    async def test_update_persists_rotated_hash_and_expiration(
        self,
        test_session: AsyncSession,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        user_session = await user_session_repository.add(
            UserSession(
                user_id=user.id,
                expires_at=now + SESSION_TIME_OFFSET,
                refresh_token_hash=REFRESH_TOKEN_HASH,
            )
        )
        session_id = user_session.id
        rotated_hash = hash_refresh_secret("rotated-refresh-secret")
        refreshed_at = now + SESSION_TIME_OFFSET
        extended_expiration = refreshed_at + SESSION_TIME_OFFSET
        user_session.refresh_token_hash = rotated_hash
        user_session.last_used_at = refreshed_at
        user_session.expires_at = extended_expiration

        updated_session = await user_session_repository.update(user_session)
        test_session.expunge_all()
        persisted_session = await test_session.get(UserSession, session_id)

        assert updated_session is user_session
        assert persisted_session is not None
        assert persisted_session.refresh_token_hash == rotated_hash
        assert persisted_session.last_used_at == refreshed_at
        assert persisted_session.expires_at == extended_expiration


class TestGetActiveWithUser:
    async def test_get_active_with_user(
        self,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        user_session = UserSession(
            user_id=user.id,
            expires_at=now + SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )

        created_session = await user_session_repository.add(user_session)

        found = await user_session_repository.get_active_with_user(created_session.id, now)

        assert found is not None

        found_session, found_user = found

        assert found_session.id == created_session.id
        assert found_user.id == user.id
        assert found_session.user_id == found_user.id

    async def test_get_active_with_user_revoked(
        self,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        user_session = UserSession(
            user_id=user.id,
            refresh_token_hash=REFRESH_TOKEN_HASH,
            expires_at=now + SESSION_TIME_OFFSET,
            revoked_at=now,
            revoked_reason=SessionRevocationReason.LOGOUT,
        )

        created_session = await user_session_repository.add(user_session)

        found = await user_session_repository.get_active_with_user(created_session.id, now)

        assert found is None

    async def test_get_active_with_user_expired(
        self,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        user_session = UserSession(
            user_id=user.id,
            expires_at=now - SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )

        created_session = await user_session_repository.add(user_session)

        found = await user_session_repository.get_active_with_user(created_session.id, now)

        assert found is None

    async def test_get_active_with_user_not_found(
        self,
        user_session_repository: UserSessionRepository,
    ):
        now = utc_now()
        session_id = uuid.uuid4()

        found = await user_session_repository.get_active_with_user(session_id, now)

        assert found is None

    async def test_get_active_with_user_expires_at_now(
        self,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        user_session = UserSession(
            user_id=user.id,
            expires_at=now,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )

        created_session = await user_session_repository.add(user_session)

        found = await user_session_repository.get_active_with_user(created_session.id, now)

        assert found is None


class TestGetActiveByUser:
    async def test_get_active_by_user_returns_only_active_sessions_for_user(
        self,
        user_repository: UserRepository,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        other_user = await user_repository.add(
            User(
                email="other@test.com",
                username="other",
                hashed_password=user.hashed_password,
            )
        )
        active_session = UserSession(
            user_id=user.id,
            expires_at=now + SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        revoked_session = UserSession(
            user_id=user.id,
            expires_at=now + SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
            revoked_at=now,
            revoked_reason=SessionRevocationReason.LOGOUT,
        )
        expired_session = UserSession(
            user_id=user.id,
            expires_at=now - SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        expiring_session = UserSession(
            user_id=user.id,
            expires_at=now,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        other_session = UserSession(
            user_id=other_user.id,
            expires_at=now + SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        sessions = [
            active_session,
            revoked_session,
            expired_session,
            expiring_session,
            other_session,
        ]
        for user_session in sessions:
            await user_session_repository.add(user_session)

        found = await user_session_repository.get_active_by_user(
            user.id, now, limit=len(sessions), offset=0
        )

        expected_session_ids = [active_session.id]

        assert [user_session.id for user_session in found] == expected_session_ids

    async def test_get_active_by_user_orders_by_last_used_at_and_id(
        self,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        session_count = 3
        recent_session_id, older_session_id, higher_session_id = sorted(
            uuid.uuid4() for _ in range(session_count)
        )
        recent_session = UserSession(
            id=recent_session_id,
            user_id=user.id,
            last_used_at=now,
            expires_at=now + SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        older_session = UserSession(
            id=older_session_id,
            user_id=user.id,
            last_used_at=now - SESSION_TIME_OFFSET,
            expires_at=now + SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        older_session_with_higher_id = UserSession(
            id=higher_session_id,
            user_id=user.id,
            last_used_at=older_session.last_used_at,
            expires_at=now + SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        sessions = [older_session, recent_session, older_session_with_higher_id]
        for user_session in sessions:
            await user_session_repository.add(user_session)

        found = await user_session_repository.get_active_by_user(
            user.id, now, limit=len(sessions), offset=0
        )

        expected_session_ids = [
            recent_session.id,
            older_session_with_higher_id.id,
            older_session.id,
        ]

        assert [user_session.id for user_session in found] == expected_session_ids

    async def test_get_active_by_user_paginates_sessions_with_equal_last_used_at(
        self,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        session_count = 3
        session_ids = sorted(uuid.uuid4() for _ in range(session_count))
        for session_id in session_ids:
            await user_session_repository.add(
                UserSession(
                    id=session_id,
                    user_id=user.id,
                    last_used_at=now,
                    expires_at=now + SESSION_TIME_OFFSET,
                    refresh_token_hash=REFRESH_TOKEN_HASH,
                )
            )
        page_size = 2
        expected_session_ids = list(reversed(session_ids))

        first_page = await user_session_repository.get_active_by_user(
            user.id, now, limit=page_size, offset=0
        )
        second_page = await user_session_repository.get_active_by_user(
            user.id, now, limit=page_size, offset=page_size
        )
        empty_page = await user_session_repository.get_active_by_user(
            user.id, now, limit=page_size, offset=session_count
        )

        assert [user_session.id for user_session in first_page] == expected_session_ids[:page_size]
        assert [user_session.id for user_session in second_page] == expected_session_ids[page_size:]
        assert empty_page == []


class TestGetByIdForUpdate:
    async def test_get_by_id_for_update(
        self,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        user_session = UserSession(
            user_id=user.id,
            expires_at=now + SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )

        created_session = await user_session_repository.add(user_session)

        found = await user_session_repository.get_by_id_for_update(created_session.id)

        assert found is not None
        assert found.id == created_session.id
        assert found.user_id == user.id

    async def test_get_by_id_for_update_revoked(
        self,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        user_session = UserSession(
            user_id=user.id,
            refresh_token_hash=REFRESH_TOKEN_HASH,
            expires_at=now + SESSION_TIME_OFFSET,
            revoked_at=now,
            revoked_reason=SessionRevocationReason.LOGOUT,
        )

        created_session = await user_session_repository.add(user_session)

        found = await user_session_repository.get_by_id_for_update(created_session.id)

        assert found is not None
        assert found.id == created_session.id
        assert found.revoked_at == now
        assert found.revoked_reason == SessionRevocationReason.LOGOUT

    async def test_get_by_id_for_update_expired(
        self,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        expires_at = now - SESSION_TIME_OFFSET
        user_session = UserSession(
            user_id=user.id,
            expires_at=expires_at,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )

        created_session = await user_session_repository.add(user_session)

        found = await user_session_repository.get_by_id_for_update(created_session.id)

        assert found is not None
        assert found.id == created_session.id
        assert found.expires_at == expires_at

    async def test_get_by_id_for_update_not_found(
        self,
        user_session_repository: UserSessionRepository,
    ):
        session_id = uuid.uuid4()

        found = await user_session_repository.get_by_id_for_update(session_id)

        assert found is None


class TestRevokeActiveExcept:
    async def test_revoke_active_except_revokes_other_active_sessions_and_returns_count(
        self,
        test_session: AsyncSession,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        reason = SessionRevocationReason.PASSWORD_CHANGED
        kept_session = await user_session_repository.add(
            UserSession(
                user_id=user.id,
                expires_at=now + SESSION_TIME_OFFSET,
                refresh_token_hash=REFRESH_TOKEN_HASH,
            )
        )
        sessions_to_revoke = [
            UserSession(
                user_id=user.id,
                expires_at=now + SESSION_TIME_OFFSET,
                refresh_token_hash=REFRESH_TOKEN_HASH,
            ),
            UserSession(
                user_id=user.id,
                expires_at=now + SESSION_TIME_OFFSET,
                refresh_token_hash=REFRESH_TOKEN_HASH,
            ),
        ]
        for user_session in sessions_to_revoke:
            await user_session_repository.add(user_session)
        expected_states = {user_session.id: (now, reason) for user_session in sessions_to_revoke}
        expected_states[kept_session.id] = (None, None)

        revoked_count = await user_session_repository.revoke_active_except(
            user.id, keep_session_id=kept_session.id, now=now, reason=reason
        )

        rows = (
            await test_session.execute(
                select(UserSession.id, UserSession.revoked_at, UserSession.revoked_reason)
            )
        ).all()
        persisted_states = {
            session_id: (revoked_at, revoked_reason)
            for session_id, revoked_at, revoked_reason in rows
        }

        assert revoked_count == len(sessions_to_revoke)
        assert persisted_states == expected_states

    async def test_revoke_active_except_preserves_other_users_and_inactive_sessions(
        self,
        test_session: AsyncSession,
        user_repository: UserRepository,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        previous_revoked_at = now - SESSION_TIME_OFFSET
        previous_reason = SessionRevocationReason.REUSE_DETECTED
        other_user = await user_repository.add(
            User(
                email="other@test.com",
                username="other",
                hashed_password=user.hashed_password,
            )
        )
        kept_session = UserSession(
            user_id=user.id,
            expires_at=now + SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        other_session = UserSession(
            user_id=other_user.id,
            expires_at=now + SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        revoked_session = UserSession(
            user_id=user.id,
            expires_at=now + SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
            revoked_at=previous_revoked_at,
            revoked_reason=previous_reason,
        )
        expired_session = UserSession(
            user_id=user.id,
            expires_at=now - SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        expiring_session = UserSession(
            user_id=user.id,
            expires_at=now,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        sessions = [
            kept_session,
            other_session,
            revoked_session,
            expired_session,
            expiring_session,
        ]
        for user_session in sessions:
            await user_session_repository.add(user_session)
        expected_states = {
            kept_session.id: (None, None),
            other_session.id: (None, None),
            revoked_session.id: (previous_revoked_at, previous_reason),
            expired_session.id: (None, None),
            expiring_session.id: (None, None),
        }
        expected_revoked_count = 0

        revoked_count = await user_session_repository.revoke_active_except(
            user.id,
            keep_session_id=kept_session.id,
            now=now,
            reason=SessionRevocationReason.PASSWORD_CHANGED,
        )

        rows = (
            await test_session.execute(
                select(UserSession.id, UserSession.revoked_at, UserSession.revoked_reason)
            )
        ).all()
        persisted_states = {
            session_id: (revoked_at, revoked_reason)
            for session_id, revoked_at, revoked_reason in rows
        }

        assert revoked_count == expected_revoked_count
        assert persisted_states == expected_states


class TestDeleteExpiredSessions:
    async def test_delete_expired_sessions_deletes_expired_session(
        self,
        test_session: AsyncSession,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        user_session = UserSession(
            user_id=user.id,
            expires_at=now - SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )

        await user_session_repository.add(user_session)

        await user_session_repository.delete_expired_sessions(user.id, now)

        remaining_session_ids = set((await test_session.scalars(select(UserSession.id))).all())

        assert remaining_session_ids == set()

    async def test_delete_expired_sessions_keeps_active_session(
        self,
        test_session: AsyncSession,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        expired_session = UserSession(
            user_id=user.id,
            expires_at=now - SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        active_session = UserSession(
            user_id=user.id,
            expires_at=now + SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )

        await user_session_repository.add(expired_session)
        await user_session_repository.add(active_session)

        await user_session_repository.delete_expired_sessions(user.id, now)

        remaining_session_ids = set((await test_session.scalars(select(UserSession.id))).all())
        expected_session_ids = {active_session.id}

        assert remaining_session_ids == expected_session_ids

    async def test_delete_expired_sessions_keeps_other_users_expired_session(
        self,
        test_session: AsyncSession,
        user_repository: UserRepository,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        other_user = await user_repository.add(
            User(
                email="other@test.com",
                username="other",
                hashed_password=user.hashed_password,
            )
        )
        expired_session = UserSession(
            user_id=user.id,
            expires_at=now - SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        other_expired_session = UserSession(
            user_id=other_user.id,
            refresh_token_hash=REFRESH_TOKEN_HASH,
            expires_at=now - SESSION_TIME_OFFSET,
        )

        await user_session_repository.add(expired_session)
        await user_session_repository.add(other_expired_session)

        await user_session_repository.delete_expired_sessions(user.id, now)

        remaining_session_ids = set((await test_session.scalars(select(UserSession.id))).all())
        expected_session_ids = {other_expired_session.id}

        assert remaining_session_ids == expected_session_ids

    async def test_delete_expired_sessions_keeps_revoked_unexpired_session(
        self,
        test_session: AsyncSession,
        user_session_repository: UserSessionRepository,
        user: User,
    ):
        now = utc_now()
        expired_session = UserSession(
            user_id=user.id,
            expires_at=now - SESSION_TIME_OFFSET,
            refresh_token_hash=REFRESH_TOKEN_HASH,
        )
        revoked_session = UserSession(
            user_id=user.id,
            refresh_token_hash=REFRESH_TOKEN_HASH,
            expires_at=now + SESSION_TIME_OFFSET,
            revoked_at=now,
            revoked_reason=SessionRevocationReason.LOGOUT,
        )

        await user_session_repository.add(expired_session)
        await user_session_repository.add(revoked_session)

        await user_session_repository.delete_expired_sessions(user.id, now)

        remaining_session_ids = set((await test_session.scalars(select(UserSession.id))).all())
        expected_session_ids = {revoked_session.id}

        assert remaining_session_ids == expected_session_ids
