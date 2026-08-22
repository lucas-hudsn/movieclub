import enum
import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


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
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submissions: Mapped[list["Submission"]] = relationship(back_populates="user")


class Cycle(Base):
    __tablename__ = "cycles"

    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(7), unique=True)  # e.g. "2026-08"
    status: Mapped[CycleStatus] = mapped_column(
        Enum(CycleStatus, name="cycle_status"), default=CycleStatus.submitting
    )
    banned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    winner_submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("submissions.id", use_alter=True), nullable=True
    )
    loser_submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("submissions.id", use_alter=True), nullable=True
    )

    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="cycle", foreign_keys="Submission.cycle_id"
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
