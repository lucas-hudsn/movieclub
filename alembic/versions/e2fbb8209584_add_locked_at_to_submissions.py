"""add locked_at to submissions

Revision ID: e2fbb8209584
Revises: c4d81f2a7b90
Create Date: 2026-08-24 15:58:25.304529

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2fbb8209584'
down_revision: Union[str, Sequence[str], None] = 'c4d81f2a7b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_foreign_key(
        "fk_cycles_winner_submission", 'cycles', 'submissions',
        ['winner_submission_id'], ['id'], use_alter=True,
    )
    op.create_foreign_key(
        "fk_cycles_loser_submission", 'cycles', 'submissions',
        ['loser_submission_id'], ['id'], use_alter=True,
    )
    op.add_column('submissions', sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('submissions', 'locked_at')
    op.drop_constraint('fk_cycles_winner_submission', 'cycles', type_='foreignkey')
    op.drop_constraint('fk_cycles_loser_submission', 'cycles', type_='foreignkey')
