"""
app/models.py - All SQLAlchemy 2.0-style ORM models for SpeakUp
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey,
    Index, Integer, String, Text, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ══════════════════════════════════════════════════════════════════════════════
#  ENUMERATIONS
# ══════════════════════════════════════════════════════════════════════════════

class UserRole(str, enum.Enum):
    CITIZEN = "CITIZEN"
    LOCAL_AUTHORITY = "LOCAL_AUTHORITY"
    MINALOC_OFFICER = "MINALOC_OFFICER"
    PRESIDENT_OFFICE_OFFICER = "PRESIDENT_OFFICE_OFFICER"
    SYS_ADMIN = "SYS_ADMIN"


class IssueStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class IssueLevel(str, enum.Enum):
    LOCAL = "LOCAL"
    MINALOC = "MINALOC"
    PRESIDENT = "PRESIDENT"


class EscalationReason(str, enum.Enum):
    CITIZEN_NOT_RESOLVED = "CITIZEN_NOT_RESOLVED"
    CITIZEN_NOT_FAIR = "CITIZEN_NOT_FAIR"
    SLA_TIMEOUT = "SLA_TIMEOUT"


class FeedbackOutcome(str, enum.Enum):
    SATISFIED = "SATISFIED"
    NOT_RESOLVED = "NOT_RESOLVED"
    NOT_FAIR = "NOT_FAIR"


# ══════════════════════════════════════════════════════════════════════════════
#  USER
# ══════════════════════════════════════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False, default=UserRole.CITIZEN)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Jurisdiction fields — only relevant for authority roles
    jurisdiction_district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    jurisdiction_sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    jurisdiction_cell: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    issues: Mapped[list["Issue"]] = relationship("Issue", back_populates="reporter", foreign_keys="Issue.reporter_user_id")
    authority_responses: Mapped[list["AuthorityResponse"]] = relationship("AuthorityResponse", back_populates="author")
    status_updates: Mapped[list["StatusUpdate"]] = relationship("StatusUpdate", back_populates="created_by")


# ══════════════════════════════════════════════════════════════════════════════
#  CATEGORY
# ══════════════════════════════════════════════════════════════════════════════

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    issues: Mapped[list["Issue"]] = relationship("Issue", back_populates="category")


# ══════════════════════════════════════════════════════════════════════════════
#  ISSUE
# ══════════════════════════════════════════════════════════════════════════════

class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    summary: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"), nullable=False)

    # Location — embedded on issue for simplicity
    district: Mapped[str] = mapped_column(String(100), nullable=False)
    sector: Mapped[str] = mapped_column(String(100), nullable=False)
    cell: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Identity / anonymity
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    reporter_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    # Status / level tracking
    current_status: Mapped[IssueStatus] = mapped_column(Enum(IssueStatus), default=IssueStatus.SUBMITTED)
    current_level: Mapped[IssueLevel] = mapped_column(Enum(IssueLevel), default=IssueLevel.LOCAL)
    level_entered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_overdue: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    category: Mapped["Category"] = relationship("Category", back_populates="issues")
    reporter: Mapped[Optional["User"]] = relationship("User", back_populates="issues", foreign_keys=[reporter_user_id])
    attachments: Mapped[list["IssueAttachment"]] = relationship("IssueAttachment", back_populates="issue", cascade="all, delete-orphan")
    status_updates: Mapped[list["StatusUpdate"]] = relationship("StatusUpdate", back_populates="issue", order_by="StatusUpdate.created_at")
    authority_responses: Mapped[list["AuthorityResponse"]] = relationship("AuthorityResponse", back_populates="issue", order_by="AuthorityResponse.created_at")
    citizen_feedbacks: Mapped[list["CitizenFeedback"]] = relationship("CitizenFeedback", back_populates="issue", order_by="CitizenFeedback.created_at")
    escalation_events: Mapped[list["EscalationEvent"]] = relationship("EscalationEvent", back_populates="issue", order_by="EscalationEvent.created_at")

    # Composite indexes for performance
    __table_args__ = (
        Index("ix_issue_level_status", "current_level", "current_status"),
        Index("ix_issue_level_entered", "level_entered_at"),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ISSUE ATTACHMENT
# ══════════════════════════════════════════════════════════════════════════════

class IssueAttachment(Base):
    __tablename__ = "issue_attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("issues.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    issue: Mapped["Issue"] = relationship("Issue", back_populates="attachments")


# ══════════════════════════════════════════════════════════════════════════════
#  STATUS UPDATE
# ══════════════════════════════════════════════════════════════════════════════

class StatusUpdate(Base):
    __tablename__ = "status_updates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("issues.id"), nullable=False)
    from_status: Mapped[IssueStatus] = mapped_column(Enum(IssueStatus), nullable=False)
    to_status: Mapped[IssueStatus] = mapped_column(Enum(IssueStatus), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    level_at_time: Mapped[IssueLevel] = mapped_column(Enum(IssueLevel), nullable=False)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    issue: Mapped["Issue"] = relationship("Issue", back_populates="status_updates")
    created_by: Mapped[Optional["User"]] = relationship("User", back_populates="status_updates")

    __table_args__ = (
        Index("ix_status_update_issue_created", "issue_id", "created_at"),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  AUTHORITY RESPONSE
# ══════════════════════════════════════════════════════════════════════════════

class AuthorityResponse(Base):
    __tablename__ = "authority_responses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("issues.id"), nullable=False)
    level: Mapped[IssueLevel] = mapped_column(Enum(IssueLevel), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    issue: Mapped["Issue"] = relationship("Issue", back_populates="authority_responses")
    author: Mapped["User"] = relationship("User", back_populates="authority_responses")

    __table_args__ = (
        Index("ix_auth_response_issue_level_created", "issue_id", "level", "created_at"),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  CITIZEN FEEDBACK
# ══════════════════════════════════════════════════════════════════════════════

class CitizenFeedback(Base):
    __tablename__ = "citizen_feedbacks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("issues.id"), nullable=False)
    level: Mapped[IssueLevel] = mapped_column(Enum(IssueLevel), nullable=False)
    outcome: Mapped[FeedbackOutcome] = mapped_column(Enum(FeedbackOutcome), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    issue: Mapped["Issue"] = relationship("Issue", back_populates="citizen_feedbacks")


# ══════════════════════════════════════════════════════════════════════════════
#  ESCALATION EVENT
# ══════════════════════════════════════════════════════════════════════════════

class EscalationEvent(Base):
    __tablename__ = "escalation_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("issues.id"), nullable=False)
    from_level: Mapped[IssueLevel] = mapped_column(Enum(IssueLevel), nullable=False)
    to_level: Mapped[IssueLevel] = mapped_column(Enum(IssueLevel), nullable=False)
    reason: Mapped[EscalationReason] = mapped_column(Enum(EscalationReason), nullable=False)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    issue: Mapped["Issue"] = relationship("Issue", back_populates="escalation_events")

    __table_args__ = (
        Index("ix_escalation_issue_created", "issue_id", "created_at"),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
