"""
app/dependencies.py - FastAPI route dependencies for auth guards
"""
from fastapi import Depends, Request, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.security import get_session_user_id


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Require a logged-in user."""
    user_id = get_session_user_id(request)
    if not user_id:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


def require_citizen(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.CITIZEN:
        raise HTTPException(status_code=403, detail="Citizens only.")
    return user


def require_authority(user: User = Depends(get_current_user)) -> User:
    if user.role not in (
        UserRole.LOCAL_AUTHORITY,
        UserRole.MINALOC_OFFICER,
        UserRole.PRESIDENT_OFFICE_OFFICER,
    ):
        raise HTTPException(status_code=403, detail="Authority access required.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.SYS_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user
