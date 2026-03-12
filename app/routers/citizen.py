"""
app/routers/citizen.py - Citizen-facing issue routes
"""
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database import get_db
from app.dependencies import require_citizen
from app.models import (
    Issue, IssueAttachment, Category, User, UserRole,
    IssueStatus, IssueLevel, CitizenFeedback, FeedbackOutcome,
    EscalationReason,
)
from app.security import get_csrf_token, validate_csrf
from app.services import escalate_issue, record_audit, save_upload, can_view_identity

router = APIRouter(prefix="/issues", tags=["citizen"])
templates = Jinja2Templates(directory="app/templates")


# ── List my issues ────────────────────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
async def list_issues(
    request: Request,
    user: User = Depends(require_citizen),
    db: Session = Depends(get_db),
):
    issues = db.execute(
        select(Issue)
        .where(Issue.reporter_user_id == user.id)
        .order_by(Issue.created_at.desc())
    ).scalars().all()
    return templates.TemplateResponse("citizen/issues_list.html", {
        "request": request, "user": user, "issues": issues
    })


# ── New issue form ────────────────────────────────────────────────────────────
@router.get("/new", response_class=HTMLResponse)
async def new_issue_get(
    request: Request,
    user: User = Depends(require_citizen),
    db: Session = Depends(get_db),
):
    categories = db.execute(select(Category).order_by(Category.name)).scalars().all()
    csrf = get_csrf_token(request)
    return templates.TemplateResponse("citizen/issue_new.html", {
        "request": request, "user": user,
        "categories": categories, "csrf_token": csrf, "error": None
    })


@router.post("/new")
async def new_issue_post(
    request: Request,
    summary: str = Form(""),
    description: str = Form(...),
    category_id: int = Form(...),
    district: str = Form(...),
    sector: str = Form(...),
    cell: str = Form(...),
    is_anonymous: str = Form("off"),
    csrf_token: str = Form(...),
    image: Optional[UploadFile] = File(None),
    user: User = Depends(require_citizen),
    db: Session = Depends(get_db),
):
    if not validate_csrf(request, csrf_token):
        return RedirectResponse("/issues/new?error=csrf", status_code=303)

    if len(description.strip()) < 20:
        categories = db.execute(select(Category).order_by(Category.name)).scalars().all()
        return templates.TemplateResponse("citizen/issue_new.html", {
            "request": request, "user": user,
            "categories": categories, "csrf_token": get_csrf_token(request),
            "error": "Description must be at least 20 characters."
        })

    issue = Issue(
        summary=summary.strip() or None,
        description=description.strip(),
        category_id=category_id,
        district=district.strip(),
        sector=sector.strip(),
        cell=cell.strip(),
        is_anonymous=(is_anonymous == "on"),
        reporter_user_id=user.id,
        current_status=IssueStatus.SUBMITTED,
        current_level=IssueLevel.LOCAL,
    )
    db.add(issue)
    db.flush()  # get issue.id before commit

    # Handle image upload
    if image and image.filename:
        try:
            content = await image.read()
            if content:
                filename = save_upload(content, image.filename, image.content_type or "")
                attachment = IssueAttachment(
                    issue_id=issue.id,
                    file_path=filename,
                    original_filename=image.filename,
                )
                db.add(attachment)
        except ValueError as e:
            db.rollback()
            categories = db.execute(select(Category).order_by(Category.name)).scalars().all()
            return templates.TemplateResponse("citizen/issue_new.html", {
                "request": request, "user": user,
                "categories": categories, "csrf_token": get_csrf_token(request),
                "error": str(e)
            })

    db.commit()
    record_audit(
        db, actor_user_id=user.id,
        action_type="ISSUE_CREATED", entity_type="Issue", entity_id=issue.id,
        metadata={"anonymous": issue.is_anonymous, "district": district},
    )
    return RedirectResponse(f"/issues/{issue.id}", status_code=303)


# ── Issue detail ──────────────────────────────────────────────────────────────
@router.get("/{issue_id}", response_class=HTMLResponse)
async def issue_detail(
    issue_id: int,
    request: Request,
    user: User = Depends(require_citizen),
    db: Session = Depends(get_db),
):
    issue = db.get(Issue, issue_id)
    # Citizens can only view their own issues (IDOR protection)
    if not issue or issue.reporter_user_id != user.id:
        return templates.TemplateResponse("errors/404.html", {"request": request}, status_code=404)

    # Can citizen submit feedback now?
    show_feedback = (
        issue.current_status == IssueStatus.RESOLVED
        and not _citizen_already_responded(issue, db)
    )

    return templates.TemplateResponse("citizen/issue_detail.html", {
        "request": request, "user": user, "issue": issue,
        "show_feedback": show_feedback,
        "csrf_token": get_csrf_token(request),
        "IssueLevel": IssueLevel,
        "IssueStatus": IssueStatus,
    })


def _citizen_already_responded(issue: Issue, db: Session) -> bool:
    """Has citizen already given feedback at current level?"""
    existing = db.execute(
        select(CitizenFeedback).where(
            CitizenFeedback.issue_id == issue.id,
            CitizenFeedback.level == issue.current_level,
        )
    ).scalars().first()
    return existing is not None


# ── Citizen feedback ──────────────────────────────────────────────────────────
@router.post("/{issue_id}/feedback")
async def submit_feedback(
    issue_id: int,
    request: Request,
    outcome: str = Form(...),
    comment: str = Form(""),
    csrf_token: str = Form(...),
    user: User = Depends(require_citizen),
    db: Session = Depends(get_db),
):
    if not validate_csrf(request, csrf_token):
        return RedirectResponse(f"/issues/{issue_id}", status_code=303)

    issue = db.get(Issue, issue_id)
    if not issue or issue.reporter_user_id != user.id:
        return RedirectResponse("/issues", status_code=303)

    if issue.current_status != IssueStatus.RESOLVED:
        return RedirectResponse(f"/issues/{issue_id}", status_code=303)

    if _citizen_already_responded(issue, db):
        return RedirectResponse(f"/issues/{issue_id}", status_code=303)

    # Validate outcome based on current level
    valid_outcomes = {
        IssueLevel.LOCAL: [FeedbackOutcome.SATISFIED.value, FeedbackOutcome.NOT_RESOLVED.value],
        IssueLevel.MINALOC: [FeedbackOutcome.SATISFIED.value, FeedbackOutcome.NOT_FAIR.value],
        IssueLevel.PRESIDENT: [FeedbackOutcome.SATISFIED.value],
    }
    allowed = valid_outcomes.get(issue.current_level, [])
    if outcome not in allowed:
        return RedirectResponse(f"/issues/{issue_id}", status_code=303)

    feedback = CitizenFeedback(
        issue_id=issue.id,
        level=issue.current_level,
        outcome=FeedbackOutcome(outcome),
        comment=comment.strip() or None,
    )
    db.add(feedback)
    db.commit()

    record_audit(
        db, actor_user_id=user.id,
        action_type="CITIZEN_FEEDBACK", entity_type="Issue", entity_id=issue.id,
        metadata={"outcome": outcome, "level": issue.current_level.value},
    )

    # Trigger escalation if needed
    if outcome == FeedbackOutcome.NOT_RESOLVED.value:
        escalate_issue(issue, EscalationReason.CITIZEN_NOT_RESOLVED, db, actor_user_id=user.id)
    elif outcome == FeedbackOutcome.NOT_FAIR.value:
        escalate_issue(issue, EscalationReason.CITIZEN_NOT_FAIR, db, actor_user_id=user.id)

    return RedirectResponse(f"/issues/{issue_id}", status_code=303)
