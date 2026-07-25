from decimal import Decimal
from typing import NamedTuple, Protocol
from datetime import date

from app.models import TransactionType

class TransactionFilterProtocol(Protocol):
    @property
    def type(self) -> TransactionType | None: ...
    @property
    def currency_code(self) -> str | None: ...
    @property
    def start_date(self) -> date | None: ...
    @property
    def end_date(self) -> date | None: ...
    @property
    def category_id(self) -> int | None: ...

class SummaryRow(NamedTuple):
    currency_code: str
    type: TransactionType
    total: Decimal


class CategorySummaryRow(NamedTuple):
    currency_code: str
    category_id: int | None
    category_name: str | None
    total: Decimal
