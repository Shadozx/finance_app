"""add timestamps to models

Revision ID: fb292ab1bb42
Revises: ec935c6ee93e
Create Date: 2026-08-18 16:34:52.144644

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'fb292ab1bb42'
down_revision: Union[str, Sequence[str], None] = 'ec935c6ee93e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # transactions is empty: no backfill needed
    op.add_column("transactions", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.add_column("transactions", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))

    # created_at already exists here: seed updated_at from it
    for table in ("accounts", "categories", "transaction_templates"):
        op.add_column(table, sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        op.execute(f"UPDATE {table} SET updated_at = created_at")
        op.alter_column(table, "updated_at", nullable=False)

    # budgets: both columns are new, nothing to derive them from
    op.add_column("budgets", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("budgets", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE budgets SET created_at = now(), updated_at = now()")
    op.alter_column("budgets", "created_at", nullable=False)
    op.alter_column("budgets", "updated_at", nullable=False)


def downgrade() -> None:
    op.drop_column('transactions', 'updated_at')
    op.drop_column('transactions', 'created_at')
    op.drop_column('transaction_templates', 'updated_at')
    op.drop_column('categories', 'updated_at')
    op.drop_column('budgets', 'updated_at')
    op.drop_column('budgets', 'created_at')
    op.drop_column('accounts', 'updated_at')
