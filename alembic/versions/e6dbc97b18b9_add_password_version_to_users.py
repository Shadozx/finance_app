"""add password version to users

Revision ID: e6dbc97b18b9
Revises: e15e6b228c4b
Create Date: 2026-10-23 16:52:48.449477

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6dbc97b18b9'
down_revision: Union[str, Sequence[str], None] = 'e15e6b228c4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('password_version', sa.Integer(), nullable=True))

    # The counter starts at 0 for existing users: it counts password changes from this
    # migration on and ignores any changes made before it
    op.execute("UPDATE users SET password_version = 0")
    op.alter_column('users', 'password_version', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'password_version')
