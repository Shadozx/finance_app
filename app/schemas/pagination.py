from typing import Generic, TypeVar

from pydantic import BaseModel, Field

MAX_RECORD_PAGE_SIZE = 100

T = TypeVar("T")


class RecordPagination(BaseModel):
    """Pagination for record lists (transactions, budgets): small pages, growing data."""

    limit: int = Field(20, ge=1, le=MAX_RECORD_PAGE_SIZE)
    offset: int = Field(0, ge=0)


class Page(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int
    has_more: bool
