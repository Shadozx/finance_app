from datetime import datetime

from sqlalchemy import String, ForeignKey, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import mapped_column, Mapped, relationship

from app.core import Base
from app.models.mixins import TimestampMixin

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import User


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100))

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    user: Mapped["User"] = relationship()

    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_category_name"),
        Index("ix_categories_user_id", "user_id"),
    )
