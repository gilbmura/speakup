"""
app/routers/authority.py - Routes for LOCAL_AUTHORITY, MINALOC_OFFICER, PRESIDENT_OFFICE_OFFICER
"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.database import get_db
from app.dependencies import require_authority
from app.models import (
    Issue, IssueLevel, IssueStatus, AuthorityResponse,
    User, UserRole, StatusUpdate,
)
from app.security import get_csrf_token, validate_csrf
from app.services import (
    get_issue_for_authority, update_issue_status,
    record_audit, can_view_identity,
)

router = APIRouter(prefix="/authority", tags=["authority"])
templates = Jinja2Templates(directory="app/templates")

# Map role → level
ROLE_TO_LEVEL = {
    UserRole.LOCAL_AUTHORITY: IssueLevel.LOCAL,
    UserRole.MINALOC_OFFICER: IssueLevel.MINALOC,
    UserRole.PRESIDENT_OFFICE_OFFICER: IssueLevel.PRESIDENT,
}


def _get_dashboard_issues(user: User, db: Session) -> list[Issue]:
    role = user.role
    level = ROLE_TO_LEVEL.get(role)
    if level is None:
        return []

    q = select(Issue).where(Issue.current_level == level)

    # LOCAL authority: filter by jurisdiction
    if role == UserRole.LOCAL_AUTHORITY:
        if user.jurisdiction_district:
            q = q.where(Issue.district.ilike(user.jurisdiction_district))

    return db.execute(q.order_by(Issue.created_at.desc())).scalars().all()


# ── Dashboard ─────────────────────────────────────────────────────────────────
@router.get("/issues", response_class=HTMLResponse)
async def authority_dashboard(
    request: Request,
    user: User = Depends(require_authority),
    db: Session = Depends(get_db),
):
    issues = _get_dashboard_issues(user, db)
    return templates.TemplateResponse("authority/dashboard.html", {
        "request": request, "user": user, "issues": issues,
        "IssueStatus": IssueStatus, "IssueLevel": IssueLevel,
    })


# ── Issue detail ──────────────────────────────────────────────────────────────
@router.get("/issues/{issue_id}", response_class=HTMLResponse)
async def authority_issue_detail(
    issue_id: int,
    request: Request,
    user: User = Depends(require_authority),
    db: Session = Depends(get_db),
):
    issue = get_issue_for_authority(issue_id, user, db)
    if not issue:
        return templates.TemplateResponse("errors/404.html", {"request": request}, status_code=404)

    show_identity = can_view_identity(user.role.value, issue, db)
    csrf = get_csrf_token(request)

    return templates.TemplateResponse("authority/issue_detail.html", {
        "request": request, "user": user, "issue": issue,
        "show_identity": show_identity,
        "csrf_token": csrf,
        "IssueStatus": IssueStatus,
        "IssueLevel": IssueLevel,
        "statuses": [s.value for s in IssueStatus],
    })


# ── Add authority response ────────────────────────────────────────────────────
@router.post("/issues/{issue_id}/respond")
async def authority_respond(
    issue_id: int,
    request: Request,
    message: str = Form(...),
    csrf_token: str = Form(...),
    user: User = Depends(require_authority),
    db: Session = Depends(get_db),
):
    if not validate_csrf(request, csrf_token):
        return RedirectResponse(f"/authority/issues/{issue_id}", status_code=303)

    issue = get_issue_for_authority(issue_id, user, db)
    if not issue:
        return RedirectResponse("/authority/issues", status_code=303)

    if len(message.strip()) < 5:
        return RedirectResponse(f"/authority/issues/{issue_id}?error=short_message", status_code=303)

    response = AuthorityResponse(
        issue_id=issue.id,
        level=issue.current_level,
        message=message.strip(),
        created_by_user_id=user.id,
    )
    db.add(response)
    db.commit()

    record_audit(
        db, actor_user_id=user.id,
        action_type="AUTHORITY_RESPONSE_ADDED", entity_type="Issue", entity_id=issue.id,
        metadata={"level": issue.current_level.value},
    )
    return RedirectResponse(f"/authority/issues/{issue_id}", status_code=303)


# ── Update status ─────────────────────────────────────────────────────────────
@router.post("/issues/{issue_id}/status")
async def authority_update_status(
    issue_id: int,
    request: Request,
    new_status: str = Form(...),
    comment: str = Form(""),
    csrf_token: str = Form(...),
    user: User = Depends(require_authority),
    db: Session = Depends(get_db),
):
    if not validate_csrf(request, csrf_token):
        return RedirectResponse(f"/authority/issues/{issue_id}", status_code=303)

    issue = get_issue_for_authority(issue_id, user, db)
    if not issue:
        return RedirectResponse("/authority/issues", status_code=303)

    try:
        status_enum = IssueStatus(new_status)
    except ValueError:
        return RedirectResponse(f"/authority/issues/{issue_id}", status_code=303)

    update_issue_status(issue, status_enum, comment.strip() or None, user.id, db)
    return RedirectResponse(f"/authority/issues/{issue_id}", status_code=303)
