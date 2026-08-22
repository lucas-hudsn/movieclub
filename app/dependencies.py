from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Cycle, CycleStatus, User
from app.security import COOKIE_NAME, read_session_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    user_id = read_session_token(token)
    if user_id is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")
    return user


def get_open_cycle(db: Session = Depends(get_db)) -> Cycle:
    cycle = db.scalars(
        select(Cycle)
        .where(Cycle.status != CycleStatus.closed)
        .order_by(Cycle.period.desc())
        .limit(1)
    ).first()
    if cycle is None:
        raise HTTPException(status_code=404, detail="no active cycle")
    return cycle
