from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Cycle, CycleStatus, Ranking, Submission, User
from app.services.scoring import tally
from app.templating import templates

router = APIRouter()


def _current_cycle(db: Session, user: User) -> Cycle | None:
    if user.team_id is None:
        return None
    return db.scalars(
        select(Cycle)
        .where(Cycle.team_id == user.team_id)
        .order_by(Cycle.period.desc())
        .limit(1)
    ).first()


def _locked_submissions(db: Session, cycle_id: int) -> list[Submission]:
    """Films that are locked in are votable; still-pending picks are hidden."""
    return db.scalars(
        select(Submission)
        .where(Submission.cycle_id == cycle_id, Submission.locked_at.is_not(None))
        .order_by(Submission.created_at)
    ).all()


def _ensure_ballot(db: Session, cycle: Cycle, user_id: int) -> list[Ranking]:
    """Create default-order (inactive) rows for any locked films missing one."""
    existing = db.scalars(
        select(Ranking).where(Ranking.cycle_id == cycle.id, Ranking.user_id == user_id)
    ).all()
    have = {r.submission_id for r in existing}
    next_pos = len(existing) + 1
    for sub in _locked_submissions(db, cycle.id):
        if sub.id not in have:
            db.add(
                Ranking(
                    cycle_id=cycle.id,
                    user_id=user_id,
                    submission_id=sub.id,
                    position=next_pos,
                    ballot_active=False,
                )
            )
            next_pos += 1
    db.commit()
    return _ballot(db, cycle.id, user_id)


def _ballot(db: Session, cycle_id: int, user_id: int) -> list[Ranking]:
    return db.scalars(
        select(Ranking)
        .where(Ranking.cycle_id == cycle_id, Ranking.user_id == user_id)
        .order_by(Ranking.position)
    ).all()


def _reject_closed(request: Request):
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request, name="partials/flash.html",
            context={"message": "this month is closed — voting is over"},
        )
    raise HTTPException(status_code=400, detail="this month is closed")


@router.get("/vote")
def vote_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = _current_cycle(db, user)
    if cycle is None:
        raise HTTPException(status_code=303, headers={"Location": "/teams/onboard"})
    db.refresh(cycle)

    locked = _locked_submissions(db, cycle.id)
    rankings = _ensure_ballot(db, cycle, user.id) if cycle.status != CycleStatus.closed else []

    results = []
    winner = None
    if cycle.status == CycleStatus.closed and cycle.winner_submission_id:
        winner = db.get(Submission, cycle.winner_submission_id)
        results = tally(cycle, db)

    return templates.TemplateResponse(
        request=request,
        name="vote.html",
        context={
            "user": user,
            "cycle": cycle,
            "cycle_id": cycle.id,
            "rankings": rankings,
            "submitted": bool(rankings) and all(r.ballot_active for r in rankings),
            "locked_count": len(locked),
            "pending_count": _pending_count(db, cycle.id),
            "results": results,
            "winner": winner,
            "CycleStatus": CycleStatus,
        },
    )


def _pending_count(db: Session, cycle_id: int) -> int:
    from sqlalchemy import func

    return db.scalar(
        select(func.count())
        .select_from(Submission)
        .where(Submission.cycle_id == cycle_id, Submission.locked_at.is_(None))
    ) or 0


@router.post("/cycles/{cycle_id}/ranking/{submission_id}/move")
def move_ranking(
    request: Request,
    cycle_id: int,
    submission_id: int,
    dir: str = "up",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or cycle.team_id != user.team_id:
        raise HTTPException(status_code=404, detail="month not found")
    if cycle.status == CycleStatus.closed:
        return _reject_closed(request)

    ballot = _ensure_ballot(db, cycle, user.id)
    idx = next((i for i, r in enumerate(ballot) if r.submission_id == submission_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="no ballot entry")

    swap = idx - 1 if dir == "up" else idx + 1
    if 0 <= swap < len(ballot):
        ballot[idx], ballot[swap] = ballot[swap], ballot[idx]
        for pos, r in enumerate(ballot, start=1):
            r.position = pos
            r.ballot_active = False
        db.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/ranking.html",
        context={"rankings": _ballot(db, cycle_id, user.id), "cycle_id": cycle_id, "submitted": False},
    )


@router.get("/cycles/{cycle_id}/ranking")
def view_ranking(
    request: Request,
    cycle_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or cycle.team_id != user.team_id:
        raise HTTPException(status_code=404, detail="month not found")
    rankings = _ballot(db, cycle_id, user.id)
    return templates.TemplateResponse(
        request=request,
        name="partials/ranking.html",
        context={
            "rankings": rankings,
            "cycle_id": cycle_id,
            "submitted": bool(rankings) and all(r.ballot_active for r in rankings),
        },
    )


@router.post("/cycles/{cycle_id}/submit-ballot")
def submit_ballot(
    request: Request,
    cycle_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lock in the ballot as-is; only submitted ballots are tallied."""
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or cycle.team_id != user.team_id:
        raise HTTPException(status_code=404, detail="month not found")
    if cycle.status == CycleStatus.closed:
        return _reject_closed(request)

    for r in db.scalars(
        select(Ranking).where(Ranking.cycle_id == cycle_id, Ranking.user_id == user.id)
    ):
        r.ballot_active = True
    db.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/ranking.html",
        context={"rankings": _ballot(db, cycle_id, user.id), "cycle_id": cycle_id, "submitted": True},
    )


@router.post("/cycles/{cycle_id}/abstain")
def abstain(
    request: Request,
    cycle_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Opt out of voting: your default order will not be tallied."""
    cycle = db.get(Cycle, cycle_id)
    if cycle is None or cycle.team_id != user.team_id:
        raise HTTPException(status_code=404, detail="month not found")
    if cycle.status == CycleStatus.closed:
        return _reject_closed(request)

    for r in db.scalars(
        select(Ranking).where(Ranking.cycle_id == cycle_id, Ranking.user_id == user.id)
    ):
        r.ballot_active = False
    db.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/ranking.html",
        context={"rankings": [], "cycle_id": cycle_id, "abstained": True},
    )
