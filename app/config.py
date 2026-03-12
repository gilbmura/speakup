"""
app/config.py - Central configuration loaded from environment / .env file
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Application ──────────────────────────────────────────────────────────────
APP_SECRET_KEY: str = os.getenv("APP_SECRET_KEY", "dev-secret-key-CHANGE-in-production")
APP_ENV: str = os.getenv("APP_ENV", "development")
APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT: int = int(os.getenv("APP_PORT", "8000"))

# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:password@localhost:3306/speakup"
)

# ── Uploads ───────────────────────────────────────────────────────────────────
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "app/static/uploads")
MAX_UPLOAD_SIZE_BYTES: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "5")) * 1024 * 1024
ALLOWED_IMAGE_TYPES: list[str] = ["image/jpeg", "image/png"]
ALLOWED_EXTENSIONS: list[str] = [".jpg", ".jpeg", ".png"]

# ── SLA ───────────────────────────────────────────────────────────────────────
SLA_DAYS: int = int(os.getenv("SLA_DAYS", "30"))
