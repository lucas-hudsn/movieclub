from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.security import COOKIE_NAME, create_session_token, hash_password, verify_password
from app.templating import templates

router = APIRouter()


@router.get("/register")
def register_form(request: Request):
    return templates.TemplateResponse(request=request, name="register.html", context={})


@router.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    name: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if not email or not name.strip() or len(password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "invalid email or password too short (8+ chars)."},
        )
    if db.scalar(select(func.count()).select_from(User).where(User.email == email)):
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "email already registered."},
        )

    is_first_user = db.scalar(select(func.count()).select_from(User)) == 0
    user = User(
        email=email,
        name=name.strip(),
        password_hash=hash_password(password),
        is_admin=is_first_user,
    )
    db.add(user)
    db.commit()

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(COOKIE_NAME, create_session_token(user.id), httponly=True, samesite="lax")
    return response


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalars(select(User).where(User.email == email.strip().lower())).first()
    if user is None or not verify_password(user.password_hash, password):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "invalid credentials."},
        )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(COOKIE_NAME, create_session_token(user.id), httponly=True, samesite="lax")
    return response


@router.post("/logout")
def logout(user: User = Depends(get_current_user)):
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response
