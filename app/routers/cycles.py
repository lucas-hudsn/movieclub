from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, is_team_admin
from app.models import Cycle, CycleStatus, Ranking, Submission, Team, User
from app.services.scoring import close_cycle, eviction_count, tally
from app.templating import templates

router = APIRouter()


def _next_period(period: str) -> str:
    year, month = (int(p) for p in period.split("-"))
    year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return f"{year:04d}-{month:02d}"


def _get_or_create_current_cycle(db: Session, team: Team) -> Cycle:
    cycle = db.scalars(
        select(Cycle)
        .where(Cycle.team_id == team.id)
        .order_by(Cycle.period.desc())
        .limit(1)
    ).first()
    if cycle is None:
        from datetime import date

        today = date.today()
        cycle = Cycle(team_id=team.id, period=f"{today.year:04d}-{today.month:02d}")
        db.add(cycle)
        db.commit()
    return cycle


def _leaderboard_rows(db: Session, team_id: int):
    from sqlalchemy import func

    wins_sq = (
        select(Submission.user_id.label("uid"), func.count().label("wins"))
        .select_from(Submission)
        .join(Cycle, Cycle.winner_submission_id == Submission.id)
        .where(Cycle.team_id == team_id)
        .group_by(Submission.user_id)
        .subquery()
    )
    losses_sq = (
        select(Submission.user_id.label("uid"), func.count().label("losses"))
        .select_from(Submission)
        .join(Cycle, Cycle.loser_submission_id == Submission.id)
        .where(Cycle.team_id == team_id)
        .group_by(Submission.user_id)
        .subquery()
    )

    return db.execute(
        select(
            User.name,
            func.coalesce(wins_sq.c.wins, 0).label("wins"),
            func.coalesce(losses_sq.c.losses, 0).label("losses"),
        )
        .where(User.team_id == team_id)
        .outerjoin(wins_sq, wins_sq.c.uid == User.id)
        .outerjoin(losses_sq, losses_sq.c.uid == User.id)
        .order_by(func.coalesce(wins_sq.c.wins, 0).desc(), func.coalesce(losses_sq.c.losses, 0), User.name)
    ).all()


@router.get("/")
def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.team_id is None:
        return RedirectResponse("/teams/onboard", status_code=303)

    cycle = _get_or_create_current_cycle(db, user.team)
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

    winner = None
    losers = []
    if cycle.status == CycleStatus.closed and cycle.winner_submission_id:
        winner = db.get(Submission, cycle.winner_submission_id)
        results_closed = tally(cycle, db)
        n_losers = min(eviction_count(cycle.team_id, db), len(results_closed) - 1)
        ordered_last = sorted(
            results_closed,
            key=lambda r: (r["points"], r["firsts"], -r["submission"].created_at.timestamp()),
        )
        losers = [row["submission"] for row in ordered_last[:n_losers]]

    banned_ids = {u.id for u in cycle.banned_users}

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "cycle": cycle,
            "team": user.team,
            "submissions": submissions,
            "my_submission": my_submission,
            "can_submit": (
                cycle.status == CycleStatus.submitting
                and my_submission is None
                and user.id not in banned_ids
            ),
            "can_unsubmit": (
                cycle.status == CycleStatus.submitting
                and my_submission is not None
                and my_submission.locked_at is None
            ),
            "banned_this_cycle": user.id in banned_ids,
            "rankings": my_ranking,
            "results": results,
            "winner": winner,
            "losers": losers,
            "leaderboard_rows": _leaderboard_rows(db, user.team_id),
            "is_cycle_admin": is_team_admin(user, user.team),
            "CycleStatus": CycleStatus,
        },
    )


@router.get("/partials/preview/{submission_id}")
def movie_preview(
    submission_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="movie not found")
    return templates.TemplateResponse(
        request=request,
        name="partials/preview.html",
        context={"submission": submission},
    )


@router.post("/admin/cycles/{cycle_id}/open-ranking")
def open_ranking(
    cycle_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or user.team_id != cycle.team_id:
        raise HTTPException(status_code=404, detail="cycle not found")
    if not is_team_admin(user, db.get(Team, cycle.team_id)):
        raise HTTPException(status_code=403, detail="only the team creator can start ranking")
    if cycle.status != CycleStatus.submitting:
        raise HTTPException(status_code=400, detail="cycle not open for submissions")

    submissions = db.scalars(
        select(Submission).where(Submission.cycle_id == cycle.id).order_by(Submission.created_at)
    ).all()
    if len(submissions) < 2:
        raise HTTPException(status_code=400, detail="need at least 2 movies to start ranking")

    members = db.scalars(select(User).where(User.team_id == cycle.team_id)).all()
    for u in members:
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or user.team_id != cycle.team_id:
        raise HTTPException(status_code=404, detail="cycle not found")
    if not is_team_admin(user, db.get(Team, cycle.team_id)):
        raise HTTPException(status_code=403, detail="only the team creator can close the cycle")
    if cycle.status != CycleStatus.ranking:
        raise HTTPException(status_code=400, detail="ranking is not open")

    winner, losers = close_cycle(cycle, db)

    next_cycle = Cycle(
        team_id=cycle.team_id,
        period=_next_period(cycle.period),
    )
    next_cycle.banned_users = [
        db.get(User, sub.user_id) for sub in losers
    ]
    db.add(next_cycle)
    db.commit()

    return RedirectResponse("/", status_code=303)


@router.get("/leaderboard")
def leaderboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.team_id is None:
        return RedirectResponse("/teams/onboard", status_code=303)
    rows = _leaderboard_rows(db, user.team_id)

    return templates.TemplateResponse(
        request=request,
        name="leaderboard.html",
        context={"user": user, "rows": rows},
    )
