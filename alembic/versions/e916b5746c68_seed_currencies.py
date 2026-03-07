"""seed_currencies

Revision ID: e916b5746c68
Revises: f61170d99ac0
Create Date: 2026-02-27 23:47:44.343768

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e916b5746c68'
down_revision: Union[str, Sequence[str], None] = 'f61170d99ac0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

currencies_table = sa.table(
    'currencies',
    sa.column('code', sa.String),
    sa.column('symbol', sa.String),
    sa.column('name', sa.String),
    sa.column('is_active', sa.Boolean),
)

CURRENCIES = [
    {"code": "UAH", "symbol": "₴", "name": "Ukrainian Hryvnia", "is_active": True},
    {"code": "USD", "symbol": "$", "name": "US Dollar", "is_active": True},
    {"code": "EUR", "symbol": "€", "name": "Euro", "is_active": True},
    {"code": "GBP", "symbol": "£", "name": "British Pound", "is_active": True},
    {"code": "PLN", "symbol": "zł", "name": "Polish Zloty", "is_active": True},
]


def upgrade() -> None:
    """Upgrade schema."""
    op.bulk_insert(currencies_table, CURRENCIES)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM currencies WHERE code IN ('UAH','USD','EUR','GBP','PLN')")
