"""
app/main.py - FastAPI application factory and startup
"""
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import APP_SECRET_KEY, UPLOAD_DIR
from app.database import engine
from app.models import Base
from app.routers import auth, citizen, authority, admin
from app.scheduler import start_scheduler

# ── Create tables (dev convenience — use Alembic for production) ──────────────
Base.metadata.create_all(bind=engine)

# ── Ensure upload directory exists ───────────────────────────────────────────
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(title="SpeakUp — Community Issue Reporting", version="1.0.0")

# Signed cookie session middleware (HTTPS in production: https_only=True)
app.add_middleware(
    SessionMiddleware,
    secret_key=APP_SECRET_KEY,
    session_cookie="speakup_session",
    max_age=60 * 60 * 8,   # 8 hours
    same_site="lax",
    https_only=False,       # Set True behind HTTPS in prod
)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(auth.router)
app.include_router(citizen.router)
app.include_router(authority.router)
app.include_router(admin.router)

# Templates (for global 404/500 error handlers)
templates = Jinja2Templates(directory="app/templates")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse("errors/404.html", {"request": request}, status_code=404)


@app.exception_handler(403)
async def forbidden(request: Request, exc):
    return templates.TemplateResponse("errors/403.html", {"request": request}, status_code=403)


# ── Startup / shutdown ────────────────────────────────────────────────────────
scheduler = None


@app.on_event("startup")
async def on_startup():
    global scheduler
    scheduler = start_scheduler()
    print("[SpeakUp] Application started.")


@app.on_event("shutdown")
async def on_shutdown():
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
    print("[SpeakUp] Application stopped.")
