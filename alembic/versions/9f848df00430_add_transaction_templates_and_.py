"""add_transaction_templates_and_constraints

Revision ID: 9f848df00430
Revises: e916b5746c68
Create Date: 2026-03-07 21:16:08.536120

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = '9f848df00430'
down_revision: Union[str, Sequence[str], None] = 'e916b5746c68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create transaction_templates table
    transaction_type_enum = ENUM('INCOME', 'EXPENSE', name='transactiontype', create_type=False)


    op.create_table(
        'transaction_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('type', transaction_type_enum, nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.String(1024), nullable=True),
        sa.Column('currency_code', sa.String(3), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('amount >= 0', name='check_template_amount_non_negative'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['currency_code'], ['currencies.code']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='uq_user_template_name')
    )

    # 2. Add unique constraint to categories
    op.create_unique_constraint('uq_user_category_name', 'categories', ['user_id', 'name'])

    # 3. Add check constraint to transactions
    op.create_check_constraint('check_transaction_amount_non_negative', 'transactions', 'amount >= 0')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('check_transaction_amount_non_negative', 'transactions', type_='check')
    op.drop_constraint('uq_user_category_name', 'categories', type_='unique')
    op.drop_table('transaction_templates')