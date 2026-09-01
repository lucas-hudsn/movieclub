from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, is_team_admin
from app.models import Cycle, CycleStatus, Ranking, Submission, Team, User, cycle_bans
from app.services.scoring import close_cycle, eviction_count, tally
from app.templating import templates

router = APIRouter()


def _next_period(period: str) -> str:
    year, month = (int(p) for p in period.split("-"))
    year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return f"{year:04d}-{month:02d}"


def _create_rankings(cycle: Cycle, db: Session):
    submissions = db.scalars(
        select(Submission).where(Submission.cycle_id == cycle.id).order_by(Submission.created_at)
    ).all()
    members = db.scalars(select(User).where(User.team_id == cycle.team_id)).all()
    existing = {
        (r.user_id, r.submission_id)
        for r in db.scalars(select(Ranking).where(Ranking.cycle_id == cycle.id)).all()
    }
    for u in members:
        for pos, sub in enumerate(submissions, start=1):
            if (u.id, sub.id) in existing:
                continue
            db.add(
                Ranking(
                    cycle_id=cycle.id,
                    user_id=u.id,
                    submission_id=sub.id,
                    position=pos,
                    ballot_active=False,
                )
            )
    db.commit()


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
    return db.execute(
        select(
            User.name,
            func.coalesce(wins_sq.c.wins, 0).label("wins"),
        )
        .where(User.team_id == team_id)
        .outerjoin(wins_sq, wins_sq.c.uid == User.id)
        .order_by(func.coalesce(wins_sq.c.wins, 0).desc(), User.name)
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

    # Calculate max submissions: min(4, team member count)
    team_member_count = db.scalar(select(func.count()).select_from(User).where(User.team_id == user.team_id)) or 0
    max_submissions = min(4, team_member_count)
    submissions_locked = cycle.submissions_locked

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
                and not submissions_locked
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
            "submissions_count": len(submissions),
            "max_submissions": max_submissions,
            "submissions_locked": submissions_locked,
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
        raise HTTPException(status_code=404, detail="month not found")
    if not is_team_admin(user, db.get(Team, cycle.team_id)):
        raise HTTPException(status_code=403, detail="only the team creator can start ranking")
    if cycle.status != CycleStatus.submitting:
        raise HTTPException(status_code=400, detail="month not open for submissions")

    submissions = db.scalars(
        select(Submission).where(Submission.cycle_id == cycle.id).order_by(Submission.created_at)
    ).all()
    if len(submissions) < 2:
        raise HTTPException(status_code=400, detail="need at least 2 movies to start ranking")

    _create_rankings(cycle, db)
    cycle.status = CycleStatus.ranking
    db.commit()
    return RedirectResponse("/vote", status_code=303)


@router.post("/admin/cycles/{cycle_id}/reopen-submissions")
def reopen_submissions(
    cycle_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or user.team_id != cycle.team_id:
        raise HTTPException(status_code=404, detail="month not found")
    if not is_team_admin(user, db.get(Team, cycle.team_id)):
        raise HTTPException(status_code=403, detail="only the team creator can reopen submissions")
    if cycle.status != CycleStatus.ranking:
        raise HTTPException(status_code=400, detail="can only reopen submissions from ranking phase")

    db.execute(delete(Ranking).where(Ranking.cycle_id == cycle.id))
    cycle.status = CycleStatus.submitting
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/admin/cycles/{cycle_id}/skip")
def skip(
    cycle_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or user.team_id != cycle.team_id:
        raise HTTPException(status_code=404, detail="month not found")
    if not is_team_admin(user, db.get(Team, cycle.team_id)):
        raise HTTPException(status_code=403, detail="only the team creator can skip")

    if cycle.status == CycleStatus.submitting:
        _create_rankings(cycle, db)
        cycle.status = CycleStatus.ranking
        db.commit()
        return RedirectResponse("/vote", status_code=303)

    if cycle.status == CycleStatus.ranking:
        winner, losers = close_cycle(cycle, db)
        next_cycle = Cycle(team_id=cycle.team_id, period=_next_period(cycle.period))
        next_cycle.banned_users = [db.get(User, sub.user_id) for sub in losers]
        db.add(next_cycle)
        db.commit()
        return RedirectResponse("/", status_code=303)

    raise HTTPException(status_code=400, detail="cannot skip a closed cycle")


@router.post("/admin/cycles/{cycle_id}/back")
def back(
    cycle_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or user.team_id != cycle.team_id:
        raise HTTPException(status_code=404, detail="month not found")
    if not is_team_admin(user, db.get(Team, cycle.team_id)):
        raise HTTPException(status_code=403, detail="only the team creator can go back")

    if cycle.status == CycleStatus.ranking:
        db.execute(delete(Ranking).where(Ranking.cycle_id == cycle.id))
        cycle.status = CycleStatus.submitting
        db.commit()
        return RedirectResponse("/", status_code=303)

    if cycle.status == CycleStatus.closed:
        next_period = _next_period(cycle.period)
        next_cycle = db.scalars(
            select(Cycle)
            .where(Cycle.team_id == cycle.team_id, Cycle.period == next_period)
            .limit(1)
        ).first()
        if next_cycle is None:
            raise HTTPException(status_code=400, detail="no next cycle to revert to")
        db.execute(delete(cycle_bans).where(cycle_bans.c.cycle_id == next_cycle.id))
        db.delete(next_cycle)
        cycle.winner_submission_id = None
        cycle.loser_submission_id = None
        cycle.status = CycleStatus.ranking
        db.commit()
        return RedirectResponse("/", status_code=303)

    raise HTTPException(status_code=400, detail="cannot go back from the submission phase")


@router.post("/admin/cycles/{cycle_id}/close")
def close(
    cycle_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or user.team_id != cycle.team_id:
        raise HTTPException(status_code=404, detail="month not found")
    if not is_team_admin(user, db.get(Team, cycle.team_id)):
        raise HTTPException(status_code=403, detail="only the team creator can close the month")
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


@router.post("/admin/cycles/{cycle_id}/lock-submissions")
def lock_submissions(
    cycle_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or user.team_id != cycle.team_id:
        raise HTTPException(status_code=404, detail="month not found")
    if not is_team_admin(user, db.get(Team, cycle.team_id)):
        raise HTTPException(status_code=403, detail="only the team creator can lock submissions")
    if cycle.status != CycleStatus.submitting:
        raise HTTPException(status_code=400, detail="can only lock during submission phase")
    if cycle.submissions_locked:
        raise HTTPException(status_code=400, detail="submissions are already locked")

    from sqlalchemy import func
    team_member_count = db.scalar(select(func.count()).select_from(User).where(User.team_id == cycle.team_id)) or 0
    max_submissions = min(4, team_member_count)
    current_submissions = db.scalar(select(func.count()).select_from(Submission).where(Submission.cycle_id == cycle_id)) or 0

    if current_submissions < max_submissions:
        raise HTTPException(status_code=400, detail=f"need {max_submissions} submissions to lock (have {current_submissions})")

    cycle.submissions_locked = True
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/admin/cycles/{cycle_id}/unlock-submissions")
def unlock_submissions(
    cycle_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or user.team_id != cycle.team_id:
        raise HTTPException(status_code=404, detail="month not found")
    if not is_team_admin(user, db.get(Team, cycle.team_id)):
        raise HTTPException(status_code=403, detail="only the team creator can unlock submissions")
    if cycle.status != CycleStatus.submitting:
        raise HTTPException(status_code=400, detail="can only unlock during submission phase")
    if not cycle.submissions_locked:
        raise HTTPException(status_code=400, detail="submissions are not locked")

    cycle.submissions_locked = False
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
