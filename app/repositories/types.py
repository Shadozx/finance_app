from decimal import Decimal
from typing import NamedTuple

from app.models import TransactionType


class SummaryRow(NamedTuple):
    currency_code: str
    type: TransactionType
    total: Decimal


class CategorySummaryRow(NamedTuple):
    currency_code: str
    category_id: int | None
    category_name: str | None
    total: Decimal
