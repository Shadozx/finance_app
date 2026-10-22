import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core import Base, utc_now
from app.models.enums import SessionRevocationReason

USER_AGENT_MAX_LENGTH = 512

# Generation of the refresh secret a new session starts with
INITIAL_REFRESH_GENERATION = 0


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    refresh_token_hash: Mapped[str] = mapped_column(String(64))

    previous_refresh_token_hash: Mapped[str | None] = mapped_column(String(64))

    # Number of the current refresh secret. Every secret written to refresh_token_hash gets
    # its own number, which never repeats and never decreases.
    refresh_generation: Mapped[int] = mapped_column(default=INITIAL_REFRESH_GENERATION)

    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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

    revoked_reason: Mapped[SessionRevocationReason | None] = mapped_column(
        Enum(SessionRevocationReason)
    )

    __table_args__ = (
        Index("ix_user_sessions_user_id", "user_id"),
        CheckConstraint(
            "(revoked_at IS NULL) = (revoked_reason IS NULL)",
            name="check_user_session_revoked_reason_matches_revoked_at",
        ),
    )
