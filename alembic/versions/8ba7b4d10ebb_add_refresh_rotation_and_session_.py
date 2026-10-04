"""add refresh rotation and session revocation fields

Revision ID: 8ba7b4d10ebb
Revises: f90bd8d1e5b1
Create Date: 2026-10-04 01:15:50.607369

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8ba7b4d10ebb'
down_revision: Union[str, Sequence[str], None] = 'f90bd8d1e5b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    revocation_reason = sa.Enum(
        'LOGOUT', 'REUSE_DETECTED', 'REVOKED_BY_USER', 'PASSWORD_CHANGED',
        name='sessionrevocationreason',
    )
    revocation_reason.create(op.get_bind())

    op.add_column('user_sessions', sa.Column('previous_refresh_token_hash', sa.String(length=64), nullable=True))
    op.add_column('user_sessions', sa.Column('rotated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('user_sessions', sa.Column('revoked_reason', revocation_reason, nullable=True))

    op.execute("UPDATE user_sessions SET revoked_reason = 'LOGOUT' WHERE revoked_at IS NOT NULL")

    op.create_check_constraint(
        "check_user_session_revoked_reason_matches_revoked_at",
        "user_sessions",
        "(revoked_at IS NULL) = (revoked_reason IS NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "check_user_session_revoked_reason_matches_revoked_at", "user_sessions", type_="check"
    )
    op.drop_column('user_sessions', 'revoked_reason')
    op.drop_column('user_sessions', 'rotated_at')
    op.drop_column('user_sessions', 'previous_refresh_token_hash')
    sa.Enum(name='sessionrevocationreason').drop(op.get_bind())
