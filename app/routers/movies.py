from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Cycle, CycleStatus, Submission, User
from app.services import omdb
from app.templating import templates

router = APIRouter()


@router.get("/partials/search")
def search_movies(
    request: Request,
    q: str,
    selected: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import select

    query = q.strip()
    if len(query) < 2:
        return templates.TemplateResponse(
            name="partials/search_results.html",
            request=request, context={"results": [], "q": query},
        )

    cycle = db.scalars(
        select(Cycle).where(Cycle.status == CycleStatus.submitting).order_by(Cycle.period.desc()).limit(1)
    ).first()

    preview = None
    if selected:
        try:
            preview = omdb.get_by_imdb_id(selected)
        except omdb.OMDBError:
            preview = None

    try:
        results = omdb.search(query)
    except omdb.OMDBError as e:
        return templates.TemplateResponse(
            name="partials/search_results.html",
            request=request, context={"results": [], "error": str(e), "q": query},
        )
    return templates.TemplateResponse(
        name="partials/search_results.html",
        request=request,
        context={
            "results": results[:6],
            "cycle_id": cycle.id if cycle else None,
            "q": query,
            "selected_id": selected,
            "preview": preview,
        },
    )


@router.post("/cycles/{cycle_id}/submissions")
def add_submission(
    request: Request,
    cycle_id: int,
    imdb_id: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    def reject(status: int, detail: str):
        if request.headers.get("HX-Request"):
            # htmx only swaps on 2xx, so surface errors as a 200 fragment
            return templates.TemplateResponse(
                request=request, name="partials/flash.html",
                context={"message": detail},
            )
        raise HTTPException(status_code=status, detail=detail)

    cycle = db.get(Cycle, cycle_id)
    if cycle is None or cycle.status != CycleStatus.submitting:
        return reject(400, "submissions are closed for this cycle")
    if cycle.banned_user_id == user.id:
        return reject(403, "you are sitting this month out")

    existing = db.scalar(
        select(Submission).where(Submission.cycle_id == cycle_id, Submission.user_id == user.id)
    )
    if existing:
        return reject(400, "you already submitted a movie this cycle")

    dupe = db.scalar(select(Submission).where(Submission.cycle_id == cycle_id, Submission.imdb_id == imdb_id))
    if dupe:
        return reject(400, "someone already picked that movie")

    try:
        movie = omdb.get_by_imdb_id(imdb_id)
    except omdb.OMDBError:
        return reject(404, "movie not found")

    db.add(Submission(cycle_id=cycle_id, user_id=user.id, **movie))
    db.commit()

    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": "/"})
    return RedirectResponse("/", status_code=303)


@router.post("/submissions/{submission_id}/delete")
def delete_submission(
    submission_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = db.get(Submission, submission_id)
    if sub is None or sub.user_id != user.id:
        raise HTTPException(status_code=404, detail="not found")
    cycle = db.get(Cycle, sub.cycle_id)
    if cycle.status != CycleStatus.submitting:
        raise HTTPException(status_code=400, detail="submissions are locked")
    db.delete(sub)
    db.commit()
    return RedirectResponse("/", status_code=303)
