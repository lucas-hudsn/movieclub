from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models import Cycle, CycleStatus, Ranking, Submission, User
from app.services.scoring import close_cycle, tally
from app.templating import templates

router = APIRouter()


def _next_period(period: str) -> str:
    year, month = (int(p) for p in period.split("-"))
    year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return f"{year:04d}-{month:02d}"


def _get_or_create_current_cycle(db: Session) -> Cycle:
    cycle = db.scalars(
        select(Cycle).order_by(Cycle.period.desc()).limit(1)
    ).first()
    if cycle is None:
        from datetime import date

        today = date.today()
        cycle = Cycle(period=f"{today.year:04d}-{today.month:02d}")
        db.add(cycle)
        db.commit()
    return cycle


@router.get("/")
def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = _get_or_create_current_cycle(db)
    db.refresh(cycle)

    submissions = db.scalars(
        select(Submission).where(Submission.cycle_id == cycle.id).order_by(Submission.created_at)
    ).all()
    my_submission = next((s for s in submissions if s.user_id == user.id), None)
    my_ranking = (
        db.scalars(
            select(Ranking)
            .where(Ranking.cycle_id == cycle.id, Ranking.user_id == user.id)
            .order_by(Ranking.position)
        ).all()
        if cycle.status == CycleStatus.ranking
        else []
    )
    results = tally(cycle, db) if cycle.status in (CycleStatus.ranking, CycleStatus.closed) else []

    winner = loser = None
    if cycle.status == CycleStatus.closed and cycle.winner_submission_id:
        winner = db.get(Submission, cycle.winner_submission_id)
        loser = db.get(Submission, cycle.loser_submission_id) if cycle.loser_submission_id else None

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "cycle": cycle,
            "submissions": submissions,
            "my_submission": my_submission,
            "can_submit": (
                cycle.status == CycleStatus.submitting
                and my_submission is None
                and cycle.banned_user_id != user.id
            ),
            "banned_this_cycle": cycle.banned_user_id == user.id,
            "rankings": my_ranking,
            "results": results,
            "winner": winner,
            "loser": loser,
            "CycleStatus": CycleStatus,
        },
    )


@router.post("/admin/cycles/{cycle_id}/open-ranking")
def open_ranking(
    cycle_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or cycle.status != CycleStatus.submitting:
        raise HTTPException(status_code=400, detail="cycle not open for submissions")

    submissions = db.scalars(
        select(Submission).where(Submission.cycle_id == cycle.id).order_by(Submission.created_at)
    ).all()
    if len(submissions) < 2:
        raise HTTPException(status_code=400, detail="need at least 2 movies to start ranking")

    users = db.scalars(select(User)).all()
    for u in users:
        for pos, sub in enumerate(submissions, start=1):
            db.add(
                Ranking(
                    cycle_id=cycle.id,
                    user_id=u.id,
                    submission_id=sub.id,
                    position=pos,
                    ballot_active=False,
                )
            )
    cycle.status = CycleStatus.ranking
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/admin/cycles/{cycle_id}/close")
def close(
    cycle_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or cycle.status != CycleStatus.ranking:
        raise HTTPException(status_code=400, detail="ranking is not open")

    winner, loser = close_cycle(cycle, db)

    next_cycle = Cycle(period=_next_period(cycle.period), banned_user_id=loser.user_id if loser else None)
    db.add(next_cycle)
    db.commit()

    return RedirectResponse("/", status_code=303)


@router.get("/leaderboard")
def leaderboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    wins_sq = (
        select(Submission.user_id.label("uid"), func.count().label("wins"))
        .select_from(Submission)
        .join(Cycle, Cycle.winner_submission_id == Submission.id)
        .group_by(Submission.user_id)
        .subquery()
    )
    losses_sq = (
        select(Submission.user_id.label("uid"), func.count().label("losses"))
        .select_from(Submission)
        .join(Cycle, Cycle.loser_submission_id == Submission.id)
        .group_by(Submission.user_id)
        .subquery()
    )

    rows = db.execute(
        select(
            User.name,
            func.coalesce(wins_sq.c.wins, 0).label("wins"),
            func.coalesce(losses_sq.c.losses, 0).label("losses"),
        )
        .outerjoin(wins_sq, wins_sq.c.uid == User.id)
        .outerjoin(losses_sq, losses_sq.c.uid == User.id)
        .order_by(func.coalesce(wins_sq.c.wins, 0).desc(), func.coalesce(losses_sq.c.losses, 0), User.name)
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="leaderboard.html",
        context={"user": user, "rows": rows},
    )
