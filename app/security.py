"""
app/security.py - Password hashing, session helpers, CSRF protection
"""
import secrets
import hashlib
from typing import Optional

from passlib.context import CryptContext
from starlette.requests import Request
from starlette.responses import Response

from app.models import UserRole

# ── Password hashing ──────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Session helpers ───────────────────────────────────────────────────────────
SESSION_USER_KEY = "user_id"
SESSION_ROLE_KEY = "user_role"
SESSION_NAME_KEY = "user_name"
CSRF_SESSION_KEY = "csrf_token"


def set_session(request: Request, user_id: int, role: str, name: str) -> None:
    request.session[SESSION_USER_KEY] = user_id
    request.session[SESSION_ROLE_KEY] = role
    request.session[SESSION_NAME_KEY] = name


def clear_session(request: Request) -> None:
    request.session.clear()


def get_session_user_id(request: Request) -> Optional[int]:
    return request.session.get(SESSION_USER_KEY)


def get_session_role(request: Request) -> Optional[str]:
    return request.session.get(SESSION_ROLE_KEY)


def get_session_name(request: Request) -> Optional[str]:
    return request.session.get(SESSION_NAME_KEY)


# ── CSRF helpers ──────────────────────────────────────────────────────────────
def get_csrf_token(request: Request) -> str:
    """Return existing CSRF token from session or generate a new one."""
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_hex(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf(request: Request, form_token: Optional[str]) -> bool:
    """Compare form CSRF token against session token."""
    session_token = request.session.get(CSRF_SESSION_KEY)
    if not session_token or not form_token:
        return False
    # Constant-time comparison
    return secrets.compare_digest(session_token, form_token)


# ── Role checks ───────────────────────────────────────────────────────────────
AUTHORITY_ROLES = {
    UserRole.LOCAL_AUTHORITY,
    UserRole.MINALOC_OFFICER,
    UserRole.PRESIDENT_OFFICE_OFFICER,
}


def is_authority(role: str) -> bool:
    return role in {r.value for r in AUTHORITY_ROLES}


def is_admin(role: str) -> bool:
    return role == UserRole.SYS_ADMIN.value
