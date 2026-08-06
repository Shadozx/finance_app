"""add settled amount and currency to transactions

Revision ID: ec935c6ee93e
Revises: 1bb92b3f825f
Create Date: 2026-08-06 19:09:52.061965

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ec935c6ee93e'
down_revision: Union[str, Sequence[str], None] = '1bb92b3f825f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("settled_amount", sa.Numeric(precision=15, scale=2), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("settled_currency_code", sa.String(length=3), nullable=True),
    )

    op.execute("UPDATE transactions SET settled_amount = amount, settled_currency_code = currency_code")

    op.alter_column("transactions", "settled_amount", nullable=False)
    op.alter_column("transactions", "settled_currency_code", nullable=False)

    op.create_foreign_key(
        "fk_transactions_settled_currency_code_currencies",
        "transactions", "currencies",
        ["settled_currency_code"], ["code"],
    )
    op.create_check_constraint(
        "check_transaction_settled_amount_non_negative",
        "transactions",
        "settled_amount >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "check_transaction_settled_amount_non_negative",
        "transactions",
        type_="check",
    )
    op.drop_constraint(
        "fk_transactions_settled_currency_code_currencies",
        "transactions",
        type_="foreignkey",
    )
    op.drop_column("transactions", "settled_currency_code")
    op.drop_column("transactions", "settled_amount")
