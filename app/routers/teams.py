import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, is_team_admin
from app.models import MAX_TEAM_SIZE, Team, User
from app.routers.cycles import _get_or_create_current_cycle
from app.templating import templates

router = APIRouter()


def new_invite_code() -> str:
    return secrets.token_urlsafe(6)


@router.get("/teams/onboard")
def onboard_form(
    request: Request,
    code: str | None = None,
    user: User = Depends(get_current_user),
):
    if user.team_id is not None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="team_onboarding.html",
        context={"code": code or ""},
    )


@router.post("/teams")
def create_team(
    request: Request,
    name: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        return templates.TemplateResponse(
            request=request,
            name="team_onboarding.html",
            context={"error": "give your team a name."},
        )
    if user.team_id is not None:
        return RedirectResponse("/", status_code=303)

    team = Team(name=name, invite_code=new_invite_code(), created_by_id=user.id)
    db.add(team)
    db.flush()
    user.team_id = team.id
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/teams/join")
def join_team(
    request: Request,
    code: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.team_id is not None:
        return RedirectResponse("/", status_code=303)

    code = code.strip()
    team = db.scalars(select(Team).where(Team.invite_code == code)).first()
    if team is None:
        return templates.TemplateResponse(
            request=request,
            name="team_onboarding.html",
            context={"error": "that invite code doesn't match any team.", "code": code},
        )
    member_count = db.scalar(
        select(func.count()).select_from(User).where(User.team_id == team.id)
    )
    if member_count >= MAX_TEAM_SIZE:
        return templates.TemplateResponse(
            request=request,
            name="team_onboarding.html",
            context={
                "error": f"teams are capped at {MAX_TEAM_SIZE} members.",
                "code": code,
            },
        )
    user.team_id = team.id
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.get("/team")
def team_settings(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.team_id is None:
        return RedirectResponse("/teams/onboard", status_code=303)
    team = db.get(Team, user.team_id)
    members = db.scalars(select(User).where(User.team_id == team.id).order_by(User.name)).all()
    owner = db.get(User, team.created_by_id)

    cycle = _get_or_create_current_cycle(db, team)
    db.refresh(cycle)

    return templates.TemplateResponse(
        request=request,
        name="team.html",
        context={
            "user": user,
            "team": team,
            "members": members,
            "owner_name": owner.name,
            "is_owner": is_team_admin(user, team),
            "cycle": cycle,
        },
    )


@router.post("/team/invite/regenerate")
def regenerate_invite(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.team_id is None:
        return RedirectResponse("/teams/onboard", status_code=303)
    team = db.get(Team, user.team_id)
    if not is_team_admin(user, team):
        raise HTTPException(status_code=403, detail="only the team creator can do that")
    team.invite_code = new_invite_code()
    db.commit()
    return RedirectResponse("/team", status_code=303)


@router.post("/team/members/{member_id}/remove")
def remove_member(
    member_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.team_id is None:
        return RedirectResponse("/teams/onboard", status_code=303)
    team = db.get(Team, user.team_id)
    if not is_team_admin(user, team):
        raise HTTPException(status_code=403, detail="only the team creator can do that")

    member = db.get(User, member_id)
    if member is None or member.team_id != team.id or member.id == user.id:
        raise HTTPException(status_code=403, detail="cannot remove that member")
    member.team_id = None
    db.commit()
    return RedirectResponse("/team", status_code=303)
