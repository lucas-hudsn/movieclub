"""teams: per-team cycles and invite-only membership

- new teams table (name + invite code + owner)
- users get a nullable team_id
- cycles move from one global cycle per period to one cycle per (team, period);
  existing data is backfilled into a single default team owned by the first user

Revision ID: c4d81f2a7b90
Revises: 9031add9d387
Create Date: 2026-08-24
"""

import secrets

import sqlalchemy as sa
from alembic import op

revision = "c4d81f2a7b90"
down_revision = "9031add9d387"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("invite_code", sa.String(length=32), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_teams_invite_code", "teams", ["invite_code"], unique=True)

    op.add_column("users", sa.Column("team_id", sa.Integer(), nullable=True))

    op.add_column("cycles", sa.Column("team_id", sa.Integer(), nullable=True))

    team_id = bind.execute(
        sa.text(
            """
            INSERT INTO teams (name, invite_code, created_by_id)
            SELECT 'movie club', :code, id FROM users ORDER BY id LIMIT 1
            RETURNING id
            """
        ),
        {"code": secrets.token_urlsafe(6)},
    ).scalar()
    if team_id is not None:
        bind.execute(sa.text("UPDATE users SET team_id = :tid WHERE team_id IS NULL"), {"tid": team_id})
        bind.execute(sa.text("UPDATE cycles SET team_id = :tid WHERE team_id IS NULL"), {"tid": team_id})

    op.alter_column("cycles", "team_id", existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key("fk_cycles_team_id_teams", "cycles", "teams", ["team_id"], ["id"])
    op.create_unique_constraint("uq_cycle_per_team_period", "cycles", ["team_id", "period"])
    op.drop_constraint("cycles_period_key", "cycles", type_="unique")

    op.create_foreign_key(
        "fk_users_team_id_teams", "users", "teams", ["team_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_team_id_teams", "users", type_="foreignkey")
    op.drop_column("users", "team_id")

    op.drop_constraint("uq_cycle_per_team_period", "cycles", type_="unique")
    op.drop_constraint("fk_cycles_team_id_teams", "cycles", type_="foreignkey")
    op.drop_column("cycles", "team_id")
    op.create_unique_constraint("cycles_period_key", "cycles", ["period"])

    op.drop_index("ix_teams_invite_code", table_name="teams")
    op.drop_table("teams")
