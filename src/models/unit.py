from sqlalchemy import String
from sqlalchemy.orm import mapped_column, Mapped

from .base import Base

class Unit(Base):

    __tablename__ = 'units'

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)