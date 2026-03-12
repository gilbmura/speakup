"""
app/services.py - Core business logic for SpeakUp

Contains:
- can_view_identity()      : anonymity / identity visibility rules
- escalate_issue()         : perform escalation, audit log
- run_sla_check()          : daily scheduler job
- record_audit()           : write AuditLog entry
- get_issue_for_authority(): IDOR-safe fetch for authorities
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.config import SLA_DAYS, UPLOAD_DIR, MAX_UPLOAD_SIZE_BYTES, ALLOWED_EXTENSIONS, ALLOWED_IMAGE_TYPES
from app.models import (
    Issue, IssueLevel, IssueStatus, EscalationEvent, EscalationReason,
    StatusUpdate, AuthorityResponse, AuditLog, User, UserRole,
    CitizenFeedback, FeedbackOutcome
)


# ══════════════════════════════════════════════════════════════════════════════
#  IDENTITY VISIBILITY
# ══════════════════════════════════════════════════════════════════════════════

def can_view_identity(viewer_role: str, issue: Issue, db: Session) -> bool:
    """
    Return True if the viewer is allowed to see reporter identity.

    Rules:
    - Not anonymous → always visible to all authority roles
    - Anonymous:
        * LOCAL_AUTHORITY: NEVER
        * MINALOC_OFFICER / PRESIDENT_OFFICE_OFFICER: allowed when
          issue is at their level OR citizen previously marked SATISFIED
        * SYS_ADMIN: always
    """
    if viewer_role == UserRole.SYS_ADMIN.value:
        return True

    if not issue.is_anonymous:
        return True  # identified issue visible to all

    # Anonymous below: LOCAL can never see
    if viewer_role == UserRole.LOCAL_AUTHORITY.value:
        return False

    # MINALOC / PRESIDENT can see during escalated handling OR after citizen is satisfied
    if viewer_role in (UserRole.MINALOC_OFFICER.value, UserRole.PRESIDENT_OFFICE_OFFICER.value):
        # Is issue currently at or above their level?
        level_order = {IssueLevel.LOCAL: 0, IssueLevel.MINALOC: 1, IssueLevel.PRESIDENT: 2}
        viewer_min_level = (
            IssueLevel.MINALOC if viewer_role == UserRole.MINALOC_OFFICER.value
            else IssueLevel.PRESIDENT
        )
        if level_order[issue.current_level] >= level_order[viewer_min_level]:
            return True

        # Has citizen ever marked SATISFIED?
        satisfied = db.execute(
            select(CitizenFeedback).where(
                and_(
                    CitizenFeedback.issue_id == issue.id,
                    CitizenFeedback.outcome == FeedbackOutcome.SATISFIED,
                )
            )
        ).scalars().first()
        return satisfied is not None

    return False


# ══════════════════════════════════════════════════════════════════════════════
#  ESCALATION
# ══════════════════════════════════════════════════════════════════════════════

NEXT_LEVEL = {
    IssueLevel.LOCAL: IssueLevel.MINALOC,
    IssueLevel.MINALOC: IssueLevel.PRESIDENT,
}


def escalate_issue(
    issue: Issue,
    reason: EscalationReason,
    db: Session,
    actor_user_id: Optional[int] = None,
) -> bool:
    """
    Escalate an issue to the next level.
    Returns True if escalation happened, False if already at max level.
    """
    if issue.current_level not in NEXT_LEVEL:
        # Already at PRESIDENT — mark overdue
        if not issue.is_overdue:
            issue.is_overdue = True
            db.commit()
            record_audit(
                db,
                actor_user_id=actor_user_id,
                action_type="ISSUE_MARKED_OVERDUE",
                entity_type="Issue",
                entity_id=issue.id,
                metadata={"reason": reason.value},
            )
        return False

    from_level = issue.current_level
    to_level = NEXT_LEVEL[from_level]

    # Create escalation event
    event = EscalationEvent(
        issue_id=issue.id,
        from_level=from_level,
        to_level=to_level,
        reason=reason,
        created_by_user_id=actor_user_id,
    )
    db.add(event)

    # Update issue
    issue.current_level = to_level
    issue.level_entered_at = datetime.now(timezone.utc).replace(tzinfo=None)
    # Reset to SUBMITTED so new authority sees fresh status
    issue.current_status = IssueStatus.SUBMITTED

    db.commit()

    record_audit(
        db,
        actor_user_id=actor_user_id,
        action_type="ISSUE_ESCALATED",
        entity_type="Issue",
        entity_id=issue.id,
        metadata={
            "from_level": from_level.value,
            "to_level": to_level.value,
            "reason": reason.value,
        },
    )
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  STATUS UPDATE
# ══════════════════════════════════════════════════════════════════════════════

def update_issue_status(
    issue: Issue,
    new_status: IssueStatus,
    comment: Optional[str],
    actor_user_id: int,
    db: Session,
) -> None:
    old_status = issue.current_status
    su = StatusUpdate(
        issue_id=issue.id,
        from_status=old_status,
        to_status=new_status,
        comment=comment,
        level_at_time=issue.current_level,
        created_by_user_id=actor_user_id,
    )
    db.add(su)
    issue.current_status = new_status
    db.commit()
    record_audit(
        db,
        actor_user_id=actor_user_id,
        action_type="STATUS_UPDATED",
        entity_type="Issue",
        entity_id=issue.id,
        metadata={"from": old_status.value, "to": new_status.value},
    )


# ══════════════════════════════════════════════════════════════════════════════
#  SLA AUTO-ESCALATION (scheduler job)
# ══════════════════════════════════════════════════════════════════════════════

def run_sla_check(db: Session) -> dict:
    """
    Runs daily. Checks all open issues for SLA violations.
    Returns a summary dict for logging.
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(days=SLA_DAYS)
    summary = {"checked": 0, "escalated": 0, "overdue": 0}

    # Fetch all non-terminal open issues
    open_issues = db.execute(
        select(Issue).where(
            Issue.current_status.not_in([IssueStatus.RESOLVED, IssueStatus.REJECTED])
        )
    ).scalars().all()

    for issue in open_issues:
        summary["checked"] += 1

        # Has there been ANY authority response at current level since level was entered?
        last_response = db.execute(
            select(AuthorityResponse)
            .where(
                and_(
                    AuthorityResponse.issue_id == issue.id,
                    AuthorityResponse.level == issue.current_level,
                    AuthorityResponse.created_at >= issue.level_entered_at,
                )
            )
            .order_by(AuthorityResponse.created_at.desc())
        ).scalars().first()

        needs_escalation = False

        if last_response is None:
            # No response at all at this level
            if issue.level_entered_at <= cutoff:
                needs_escalation = True
        else:
            # Has a response, but check if last response was > 30 days ago
            if last_response.created_at <= cutoff:
                needs_escalation = True

        if needs_escalation:
            if issue.current_level == IssueLevel.PRESIDENT:
                if not issue.is_overdue:
                    issue.is_overdue = True
                    db.commit()
                    record_audit(
                        db,
                        actor_user_id=None,
                        action_type="ISSUE_MARKED_OVERDUE",
                        entity_type="Issue",
                        entity_id=issue.id,
                        metadata={"reason": "SLA_TIMEOUT"},
                    )
                    summary["overdue"] += 1
            else:
                escalated = escalate_issue(
                    issue=issue,
                    reason=EscalationReason.SLA_TIMEOUT,
                    db=db,
                    actor_user_id=None,
                )
                if escalated:
                    summary["escalated"] += 1

    print(f"[SLA Check] {now.isoformat()} — {summary}")
    return summary


# ══════════════════════════════════════════════════════════════════════════════
#  IDOR-SAFE ISSUE FETCH
# ══════════════════════════════════════════════════════════════════════════════

def get_issue_for_authority(issue_id: int, user: User, db: Session) -> Optional[Issue]:
    """
    Fetch issue only if it matches authority's jurisdiction and level.
    Returns None if not allowed.
    """
    issue = db.get(Issue, issue_id)
    if not issue:
        return None

    role = user.role

    # MINALOC and PRESIDENT see all issues at their level (national scope)
    if role == UserRole.MINALOC_OFFICER:
        if issue.current_level != IssueLevel.MINALOC:
            return None
        return issue

    if role == UserRole.PRESIDENT_OFFICE_OFFICER:
        if issue.current_level != IssueLevel.PRESIDENT:
            return None
        return issue

    if role == UserRole.LOCAL_AUTHORITY:
        if issue.current_level != IssueLevel.LOCAL:
            return None
        # Match jurisdiction
        if user.jurisdiction_district and issue.district.lower() != user.jurisdiction_district.lower():
            return None
        return issue

    if role == UserRole.SYS_ADMIN:
        return issue

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════

def record_audit(
    db: Session,
    action_type: str,
    entity_type: str,
    actor_user_id: Optional[int] = None,
    entity_id: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> None:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(entry)
    db.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  FILE UPLOAD
# ══════════════════════════════════════════════════════════════════════════════

def save_upload(file_bytes: bytes, original_filename: str, content_type: str) -> str:
    """
    Save uploaded file with randomized name.
    Returns the relative path under UPLOAD_DIR.
    Raises ValueError on validation failure.
    """
    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise ValueError("File exceeds maximum allowed size of 5MB.")

    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError("Only JPG and PNG images are allowed.")

    ext = os.path.splitext(original_filename)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Invalid file extension.")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(UPLOAD_DIR, safe_name)

    with open(dest_path, "wb") as f:
        f.write(file_bytes)

    return safe_name  # store only filename; serve from /static/uploads/
