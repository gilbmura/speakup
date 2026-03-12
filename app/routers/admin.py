"""
app/routers/admin.py - SYS_ADMIN routes: users, categories, reports, audit log
"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, func, text

from app.database import get_db, SessionLocal
from app.dependencies import require_admin
from app.models import (
    User, UserRole, Category, Issue, IssueStatus, IssueLevel,
    AuditLog, AuthorityResponse, StatusUpdate,
)
from app.security import hash_password, get_csrf_token, validate_csrf
from app.services import run_sla_check, record_audit

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


# ── Users ─────────────────────────────────────────────────────────────────────
@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.execute(select(User).order_by(User.created_at.desc())).scalars().all()
    csrf = get_csrf_token(request)
    return templates.TemplateResponse("admin/users.html", {
        "request": request, "user": user, "users": users,
        "roles": [r.value for r in UserRole], "csrf_token": csrf,
    })


@router.post("/users/create")
async def admin_create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    password: str = Form(...),
    role: str = Form(...),
    jurisdiction_district: str = Form(""),
    jurisdiction_sector: str = Form(""),
    jurisdiction_cell: str = Form(""),
    csrf_token: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not validate_csrf(request, csrf_token):
        return RedirectResponse("/admin/users", status_code=303)

    existing = db.execute(select(User).where(User.email == email.lower().strip())).scalars().first()
    if existing:
        return RedirectResponse("/admin/users?error=email_taken", status_code=303)

    new_user = User(
        name=name.strip(),
        email=email.lower().strip(),
        phone=phone.strip() or None,
        password_hash=hash_password(password),
        role=UserRole(role),
        jurisdiction_district=jurisdiction_district.strip() or None,
        jurisdiction_sector=jurisdiction_sector.strip() or None,
        jurisdiction_cell=jurisdiction_cell.strip() or None,
    )
    db.add(new_user)
    db.commit()
    record_audit(db, actor_user_id=user.id, action_type="USER_CREATED",
                 entity_type="User", entity_id=new_user.id, metadata={"role": role})
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{target_id}/toggle")
async def admin_toggle_user(
    target_id: int,
    request: Request,
    csrf_token: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not validate_csrf(request, csrf_token):
        return RedirectResponse("/admin/users", status_code=303)
    target = db.get(User, target_id)
    if target and target.id != user.id:
        target.is_active = not target.is_active
        db.commit()
        record_audit(db, actor_user_id=user.id,
                     action_type="USER_TOGGLED", entity_type="User",
                     entity_id=target.id, metadata={"is_active": target.is_active})
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{target_id}/role")
async def admin_change_role(
    target_id: int,
    request: Request,
    role: str = Form(...),
    jurisdiction_district: str = Form(""),
    jurisdiction_sector: str = Form(""),
    jurisdiction_cell: str = Form(""),
    csrf_token: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not validate_csrf(request, csrf_token):
        return RedirectResponse("/admin/users", status_code=303)
    target = db.get(User, target_id)
    if target:
        target.role = UserRole(role)
        target.jurisdiction_district = jurisdiction_district.strip() or None
        target.jurisdiction_sector = jurisdiction_sector.strip() or None
        target.jurisdiction_cell = jurisdiction_cell.strip() or None
        db.commit()
        record_audit(db, actor_user_id=user.id,
                     action_type="USER_ROLE_CHANGED", entity_type="User",
                     entity_id=target.id, metadata={"new_role": role})
    return RedirectResponse("/admin/users", status_code=303)


# ── Categories ────────────────────────────────────────────────────────────────
@router.get("/categories", response_class=HTMLResponse)
async def admin_categories(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cats = db.execute(select(Category).order_by(Category.name)).scalars().all()
    csrf = get_csrf_token(request)
    return templates.TemplateResponse("admin/categories.html", {
        "request": request, "user": user, "categories": cats, "csrf_token": csrf,
    })


@router.post("/categories/create")
async def admin_create_category(
    request: Request,
    name: str = Form(...),
    csrf_token: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not validate_csrf(request, csrf_token):
        return RedirectResponse("/admin/categories", status_code=303)
    cat = Category(name=name.strip())
    db.add(cat)
    db.commit()
    return RedirectResponse("/admin/categories", status_code=303)


@router.post("/categories/{cat_id}/delete")
async def admin_delete_category(
    cat_id: int,
    request: Request,
    csrf_token: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not validate_csrf(request, csrf_token):
        return RedirectResponse("/admin/categories", status_code=303)
    cat = db.get(Category, cat_id)
    if cat:
        db.delete(cat)
        db.commit()
    return RedirectResponse("/admin/categories", status_code=303)


# ── Reports / Analytics ───────────────────────────────────────────────────────
@router.get("/reports", response_class=HTMLResponse)
async def admin_reports(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # Issues by category
    by_category = db.execute(
        select(Category.name, func.count(Issue.id).label("count"))
        .join(Issue, Issue.category_id == Category.id, isouter=True)
        .group_by(Category.name)
        .order_by(func.count(Issue.id).desc())
    ).all()

    # Issues by status
    by_status = db.execute(
        select(Issue.current_status, func.count(Issue.id).label("count"))
        .group_by(Issue.current_status)
    ).all()

    # Issues by level
    by_level = db.execute(
        select(Issue.current_level, func.count(Issue.id).label("count"))
        .group_by(Issue.current_level)
    ).all()

    # Overdue count
    overdue_count = db.execute(
        select(func.count(Issue.id)).where(Issue.is_overdue == True)
    ).scalar()

    total_issues = db.execute(select(func.count(Issue.id))).scalar()

    csrf = get_csrf_token(request)
    return templates.TemplateResponse("admin/reports.html", {
        "request": request, "user": user,
        "by_category": by_category,
        "by_status": by_status,
        "by_level": by_level,
        "overdue_count": overdue_count,
        "total_issues": total_issues,
        "csrf_token": csrf,
    })


# ── Audit Log ─────────────────────────────────────────────────────────────────
@router.get("/audit", response_class=HTMLResponse)
async def admin_audit(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    logs = db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500)
    ).scalars().all()
    return templates.TemplateResponse("admin/audit.html", {
        "request": request, "user": user, "logs": logs,
    })


# ── Manual SLA trigger (admin only) ──────────────────────────────────────────
@router.post("/run-sla-check")
async def manual_sla_check(
    request: Request,
    csrf_token: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not validate_csrf(request, csrf_token):
        return RedirectResponse("/admin/reports", status_code=303)
    summary = run_sla_check(db)
    record_audit(db, actor_user_id=user.id,
                 action_type="MANUAL_SLA_CHECK", entity_type="System",
                 metadata=summary)
    return RedirectResponse(f"/admin/reports?sla=done&checked={summary['checked']}&escalated={summary['escalated']}", status_code=303)
