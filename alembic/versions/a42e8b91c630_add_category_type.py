"""add category type

Revision ID: a42e8b91c630
Revises: d9da74d03578
Create Date: 2026-09-19 08:27:04.348511+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a42e8b91c630'
down_revision: Union[str, Sequence[str], None] = 'd9da74d03578'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Derive category types from regular transaction history."""
    category_type = sa.Enum('EXPENSE', 'INCOME', 'ANY', name='categorytype')
    category_type.create(op.get_bind())

    op.add_column('categories', sa.Column('type', category_type, nullable=True))

    # Both direct categories and splits vote; templates and service operations do not.
    op.execute("""
        WITH category_history AS (
            SELECT category_id, user_id, type
            FROM transactions
            WHERE kind = 'REGULAR' AND category_id IS NOT NULL

            UNION ALL

            SELECT splits.category_id, transactions.user_id, transactions.type
            FROM transaction_splits AS splits
            JOIN transactions ON transactions.id = splits.transaction_id
            WHERE transactions.kind = 'REGULAR' AND splits.category_id IS NOT NULL
        ), category_types AS (
            SELECT categories.id,
                CASE
                    WHEN bool_or(history.type = 'EXPENSE')
                        AND NOT bool_or(history.type = 'INCOME') THEN 'EXPENSE'
                    WHEN bool_or(history.type = 'INCOME')
                        AND NOT bool_or(history.type = 'EXPENSE') THEN 'INCOME'
                    ELSE 'ANY'
                END AS type
            FROM categories
            LEFT JOIN category_history AS history
                ON history.category_id = categories.id
                AND history.user_id = categories.user_id
            GROUP BY categories.id
        )
        UPDATE categories
        SET type = category_types.type::categorytype
        FROM category_types
        WHERE categories.id = category_types.id
            AND categories.type IS NULL
    """)

    op.alter_column('categories', 'type', nullable=False)


def downgrade() -> None:
    """Remove category types, including the PostgreSQL enum."""
    op.drop_column('categories', 'type')
    sa.Enum(name='categorytype').drop(op.get_bind())
