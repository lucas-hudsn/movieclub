import enum
import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


MAX_TEAM_SIZE = 6

cycle_bans = Table(
    "cycle_bans",
    Base.metadata,
    Column("cycle_id", ForeignKey("cycles.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
)


class CycleStatus(str, enum.Enum):
    submitting = "submitting"
    ranking = "ranking"
    closed = "closed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", use_alter=True), nullable=True
    )
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submissions: Mapped[list["Submission"]] = relationship(back_populates="user")
    team: Mapped["Team"] = relationship(foreign_keys=[team_id])
    banned_in_cycles: Mapped[list["Cycle"]] = relationship(
        secondary="cycle_bans", back_populates="banned_users"
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=func.now())

    members: Mapped[list[User]] = relationship(foreign_keys="User.team_id", viewonly=True)


class Cycle(Base):
    __tablename__ = "cycles"
    __table_args__ = (UniqueConstraint("team_id", "period", name="uq_cycle_per_team_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    period: Mapped[str] = mapped_column(String(7))  # e.g. "2026-08"
    status: Mapped[CycleStatus] = mapped_column(
        Enum(CycleStatus, name="cycle_status"), default=CycleStatus.submitting
    )
    winner_submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("submissions.id", use_alter=True), nullable=True
    )
    loser_submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("submissions.id", use_alter=True), nullable=True
    )
    submissions_locked: Mapped[bool] = mapped_column(Boolean, default=False)

    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="cycle", foreign_keys="Submission.cycle_id"
    )
    banned_users: Mapped[list["User"]] = relationship(
        secondary="cycle_bans", back_populates="banned_in_cycles"
    )


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("cycle_id", "user_id", name="uq_one_submission_per_user"),
        UniqueConstraint("cycle_id", "imdb_id", name="uq_one_submission_per_movie"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("cycles.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    imdb_id: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(255))
    year: Mapped[str] = mapped_column(String(10))
    poster_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    plot: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cycle: Mapped[Cycle] = relationship(back_populates="submissions", foreign_keys=[cycle_id])
    user: Mapped[User] = relationship(back_populates="submissions")


class Ranking(Base):
    __tablename__ = "rankings"
    __table_args__ = (
        UniqueConstraint("cycle_id", "user_id", "submission_id", name="uq_rank_once"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("cycles.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"))
    position: Mapped[int] = mapped_column(Integer)  # 1 = best
    ballot_active: Mapped[bool] = mapped_column(Boolean, default=False)

    submission: Mapped[Submission] = relationship()
