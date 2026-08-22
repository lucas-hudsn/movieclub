from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Ranking, User
from app.templating import templates

router = APIRouter()


def _ballot(db: Session, cycle_id: int, user_id: int) -> list[Ranking]:
    return db.scalars(
        select(Ranking)
        .where(Ranking.cycle_id == cycle_id, Ranking.user_id == user_id)
        .order_by(Ranking.position)
    ).all()


@router.post("/cycles/{cycle_id}/ranking/{submission_id}/move")
def move_ranking(
    request: Request,
    cycle_id: int,
    submission_id: int,
    dir: str = "up",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ballot = _ballot(db, cycle_id, user.id)
    idx = next((i for i, r in enumerate(ballot) if r.submission_id == submission_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="no ballot entry")

    swap = idx - 1 if dir == "up" else idx + 1
    if 0 <= swap < len(ballot):
        ballot[idx], ballot[swap] = ballot[swap], ballot[idx]
        for pos, r in enumerate(ballot, start=1):
            r.position = pos
            r.ballot_active = True
        db.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/ranking.html",
        context={"rankings": _ballot(db, cycle_id, user.id), "cycle_id": cycle_id},
    )


@router.get("/cycles/{cycle_id}/ranking")
def view_ranking(
    request: Request,
    cycle_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request=request,
        name="partials/ranking.html",
        context={"rankings": _ballot(db, cycle_id, user.id), "cycle_id": cycle_id},
    )


@router.post("/cycles/{cycle_id}/abstain")
def abstain(
    request: Request,
    cycle_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Opt out of voting: your default order will not be tallied."""
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
