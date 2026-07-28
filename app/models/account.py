from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import mapped_column, Mapped, relationship

from app.core import Base

if TYPE_CHECKING:
    from app.models import User


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100))

    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"))

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    user: Mapped["User"] = relationship()

    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_account_name"),
        Index("ix_accounts_user_id", "user_id"),
    )