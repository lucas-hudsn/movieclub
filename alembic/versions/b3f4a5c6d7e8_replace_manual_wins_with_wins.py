"""replace manual_wins with wins

Revision ID: b3f4a5c6d7e8
Revises: 48bc21e93b29
Create Date: 2026-09-01 12:16:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f4a5c6d7e8'
down_revision: Union[str, Sequence[str], None] = '48bc21e93b29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add wins column, backfill from manual_wins + computed wins, drop manual_wins."""
    op.add_column('users', sa.Column('wins', sa.Integer(), nullable=False, server_default='0'))

    # Backfill: start with manual_wins, then add computed wins from cycles
    op.execute("UPDATE users SET wins = manual_wins")
    op.execute("""
        UPDATE users SET wins = wins + sub.cnt
        FROM (
            SELECT submissions.user_id AS uid, COUNT(*) AS cnt
            FROM cycles
            JOIN submissions ON cycles.winner_submission_id = submissions.id
            GROUP BY submissions.user_id
        ) AS sub
        WHERE sub.uid = users.id
    """)

    op.drop_column('users', 'manual_wins')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', sa.Column('manual_wins', sa.Integer(), nullable=False, server_default='0'))
    op.execute("""
        UPDATE users SET manual_wins = 0
    """)
    op.drop_column('users', 'wins')
