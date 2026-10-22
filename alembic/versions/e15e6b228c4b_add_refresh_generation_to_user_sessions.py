"""add refresh generation to user sessions

Revision ID: e15e6b228c4b
Revises: 8ba7b4d10ebb
Create Date: 2026-10-22 11:14:54.645435

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e15e6b228c4b'
down_revision: Union[str, Sequence[str], None] = '8ba7b4d10ebb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user_sessions', sa.Column('refresh_generation', sa.Integer(), nullable=True))

    # Existing sessions hold their first secret, which is generation 0
    op.execute("UPDATE user_sessions SET refresh_generation = 0")
    op.alter_column('user_sessions', 'refresh_generation', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('user_sessions', 'refresh_generation')
