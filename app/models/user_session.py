import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core import Base, utc_now

USER_AGENT_MAX_LENGTH = 512


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    refresh_token_hash: Mapped[str] = mapped_column(String(64))

    user_agent: Mapped[str | None] = mapped_column(String(USER_AGENT_MAX_LENGTH))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    __table_args__ = (Index("ix_user_sessions_user_id", "user_id"),)
