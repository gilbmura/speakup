"""
app/routers/auth.py - Register, login, logout routes
"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database import get_db
from app.models import User, UserRole
from app.security import (
    hash_password, verify_password,
    set_session, clear_session,
    get_csrf_token, validate_csrf,
    get_session_user_id,
)
from app.services import record_audit

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user_id = get_session_user_id(request)
    return templates.TemplateResponse("home.html", {"request": request, "user_id": user_id})


@router.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    csrf = get_csrf_token(request)
    return templates.TemplateResponse("auth/register.html", {"request": request, "csrf_token": csrf, "error": None})


@router.post("/register")
async def register_post(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    if not validate_csrf(request, csrf_token):
        return templates.TemplateResponse("auth/register.html", {
            "request": request, "csrf_token": get_csrf_token(request),
            "error": "Invalid security token. Please try again."
        })

    # Check duplicate email
    existing = db.execute(select(User).where(User.email == email.lower().strip())).scalars().first()
    if existing:
        return templates.TemplateResponse("auth/register.html", {
            "request": request, "csrf_token": get_csrf_token(request),
            "error": "Email already registered."
        })

    if len(password) < 8:
        return templates.TemplateResponse("auth/register.html", {
            "request": request, "csrf_token": get_csrf_token(request),
            "error": "Password must be at least 8 characters."
        })

    user = User(
        name=name.strip(),
        email=email.lower().strip(),
        phone=phone.strip() or None,
        password_hash=hash_password(password),
        role=UserRole.CITIZEN,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    record_audit(db, action_type="USER_REGISTERED", entity_type="User",
                 actor_user_id=user.id, entity_id=user.id)

    set_session(request, user.id, user.role.value, user.name)
    return RedirectResponse("/issues", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    csrf = get_csrf_token(request)
    return templates.TemplateResponse("auth/login.html", {"request": request, "csrf_token": csrf, "error": None})


@router.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    if not validate_csrf(request, csrf_token):
        return templates.TemplateResponse("auth/login.html", {
            "request": request, "csrf_token": get_csrf_token(request),
            "error": "Invalid security token."
        })

    user = db.execute(select(User).where(User.email == email.lower().strip())).scalars().first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("auth/login.html", {
            "request": request, "csrf_token": get_csrf_token(request),
            "error": "Invalid email or password."
        })

    if not user.is_active:
        return templates.TemplateResponse("auth/login.html", {
            "request": request, "csrf_token": get_csrf_token(request),
            "error": "Your account is disabled. Contact the administrator."
        })

    set_session(request, user.id, user.role.value, user.name)
    record_audit(db, action_type="USER_LOGIN", entity_type="User",
                 actor_user_id=user.id, entity_id=user.id)

    # Role-based redirect
    role = user.role
    if role == UserRole.CITIZEN:
        return RedirectResponse("/issues", status_code=303)
    elif role == UserRole.SYS_ADMIN:
        return RedirectResponse("/admin/users", status_code=303)
    else:
        return RedirectResponse("/authority/issues", status_code=303)


@router.get("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    user_id = get_session_user_id(request)
    if user_id:
        record_audit(db, action_type="USER_LOGOUT", entity_type="User",
                     actor_user_id=user_id, entity_id=user_id)
    clear_session(request)
    return RedirectResponse("/login", status_code=303)
