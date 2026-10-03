import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import utc_now
from app.core.security import hash_refresh_secret
from app.models import User, UserSession
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
        )

        await user_session_repository.add(expired_session)
        await user_session_repository.add(revoked_session)

        await user_session_repository.delete_expired_sessions(user.id, now)

        remaining_session_ids = set((await test_session.scalars(select(UserSession.id))).all())
        expected_session_ids = {revoked_session.id}

        assert remaining_session_ids == expected_session_ids
