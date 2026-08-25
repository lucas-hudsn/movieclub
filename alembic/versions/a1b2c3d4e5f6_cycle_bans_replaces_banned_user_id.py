"""cycle_bans replaces banned_user_id

Revision ID: a1b2c3d4e5f6
Revises: e2fbb8209584
Create Date: 2026-08-25

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "e2fbb8209584"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cycle_bans",
        sa.Column("cycle_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("cycle_id", "user_id"),
    )
    # carry over existing single bans before dropping the column
    op.execute(
        "INSERT INTO cycle_bans (cycle_id, user_id) "
        "SELECT id, banned_user_id FROM cycles WHERE banned_user_id IS NOT NULL"
    )
    op.drop_constraint("cycles_banned_user_id_fkey", "cycles", type_="foreignkey")
    op.drop_column("cycles", "banned_user_id")


def downgrade() -> None:
    op.add_column(
        "cycles",
        sa.Column("banned_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "cycles_banned_user_id_fkey", "cycles", "users", ["banned_user_id"], ["id"]
    )
    op.execute(
        "UPDATE cycles SET banned_user_id = cb.user_id "
        "FROM (SELECT DISTINCT ON (cycle_id) cycle_id, user_id FROM cycle_bans) AS cb "
        "WHERE cycles.id = cb.cycle_id"
    )
    op.drop_table("cycle_bans")
