from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models import User


class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100))

    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"))

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    user: Mapped["User"] = relationship()

    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_account_name"),
        Index("ix_accounts_user_id", "user_id"),
    )
