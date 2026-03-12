# SpeakUp — Community Issue Reporting & Tracking Platform

A production-ready MVP for local governance in Africa. Citizens report issues, authorities respond, and a full escalation chain ensures accountability — from Local Authority → MINALOC → President's Office.

---

## Quick Start

### Option A: Docker (recommended — one command)

**Prerequisites:** Docker Desktop installed and running.

```bash
docker compose up --build
```

Then open: **http://localhost:8000**

Seed data is loaded automatically on container startup (safe to run repeatedly; seeding is idempotent).

### Docker services and ports

- `app` service (`speakup_app`) exposed on **http://localhost:8000**
- `db` service (`speakup_db`) exposed on **localhost:3307** (mapped to container `3306`)

Useful commands:

```bash
docker compose ps
docker compose logs -f app
docker compose down
```

---

### Option B: Local Windows (no Docker)

**Prerequisites:**
- Python 3.11+ (download from python.org — check "Add to PATH")
- MySQL 8 (download from mysql.com or use XAMPP/WAMP)

**Step 1 — Run setup:**
```bat
setup.bat
```

**Step 2 — Create the MySQL database:**

Open MySQL Workbench or command prompt:
```sql
CREATE DATABASE speakup CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

**Step 3 — Edit `.env`:**

Open the `.env` file that was created by setup.bat and update:
```env
DATABASE_URL=mysql+pymysql://root:YOURPASSWORD@localhost:3306/speakup
APP_SECRET_KEY=any-long-random-string-here
```

**Step 4 — Seed the database:**
```bat
.venv\Scripts\python.exe seed.py
```

**Step 5 — Start the app:**
```bat
run.bat
```

Open: **http://localhost:8000**

---

## Test Users (created by seed.py)

| Role | Email | Password |
|---|---|---|
| SYS_ADMIN | admin@speakup.rw | Admin123! |
| LOCAL_AUTHORITY (Gasabo) | local@speakup.rw | Local123! |
| MINALOC_OFFICER | minaloc@speakup.rw | Minaloc123! |
| PRESIDENT_OFFICE_OFFICER | presoffice@speakup.rw | Pres123! |
| CITIZEN (demo) | citizen@speakup.rw | Citizen123! |

---

## Project Structure

```
speakup/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI app, middleware, startup
│   ├── config.py         # Environment config
│   ├── database.py       # SQLAlchemy engine + session
│   ├── models.py         # All ORM models
│   ├── services.py       # Business logic (escalation, identity, SLA)
│   ├── security.py       # Passwords, sessions, CSRF
│   ├── dependencies.py   # FastAPI route guards
│   ├── scheduler.py      # APScheduler SLA job
│   ├── routers/
│   │   ├── auth.py       # /register /login /logout
│   │   ├── citizen.py    # /issues/*
│   │   ├── authority.py  # /authority/*
│   │   └── admin.py      # /admin/*
│   ├── templates/
│   │   ├── base.html
│   │   ├── home.html
│   │   ├── auth/         # login.html, register.html
│   │   ├── citizen/      # issues_list, issue_new, issue_detail
│   │   ├── authority/    # dashboard, issue_detail
│   │   ├── admin/        # users, categories, reports, audit
│   │   └── errors/       # 404.html, 403.html
│   └── static/
│       └── uploads/      # Uploaded images stored here (created at runtime/build if missing)
├── alembic/
│   ├── env.py
│   └── versions/
├── alembic.ini
├── seed.py               # Seed categories + default users
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── setup.bat             # Windows local setup
└── run.bat               # Windows start script
```

---

## How Escalation Works

Issues follow a 3-level hierarchy: **LOCAL → MINALOC → PRESIDENT**

### Citizen-driven escalation
1. Authority marks issue **Resolved** at LOCAL level
2. Citizen sees a feedback panel — options: **Satisfied** or **Not Resolved**
3. If "Not Resolved" → issue escalates to MINALOC level
4. After MINALOC resolves — citizen sees: **Satisfied** or **Not Fair**
5. If "Not Fair" → escalates to PRESIDENT (highest level, no further escalation)

### SLA auto-escalation (runs daily at 02:00 UTC)
- If no `AuthorityResponse` exists at the current level for **30+ days** since the issue entered that level → system auto-escalates
- If issue is at PRESIDENT and still no action after 30 days → flagged **OVERDUE**
- Admin can trigger SLA check manually: **Admin → Reports → Run SLA Check**

The SLA timer resets every time an issue moves to a new level (`level_entered_at` is updated).

---

## How Anonymity / Identity Visibility Works

When a citizen submits an issue with **"Submit Anonymously"** checked:

| Viewer Role | Can See Identity? |
|---|---|
| LOCAL_AUTHORITY | ❌ Never |
| MINALOC_OFFICER | ✅ When issue is at MINALOC level or higher, OR citizen marked Satisfied |
| PRESIDENT_OFFICE_OFFICER | ✅ When issue is at PRESIDENT level, OR citizen marked Satisfied |
| SYS_ADMIN | ✅ Always |

This is enforced in both the **backend** (`services.can_view_identity()`) and the **templates** (conditional rendering).

For **non-anonymous** issues, all roles can see the reporter identity normally.

---

## Security Features

- **Passwords**: bcrypt hashed via passlib
- **Sessions**: Signed cookie sessions via Starlette SessionMiddleware (8-hour TTL)
- **CSRF**: Token-in-session + hidden form field on all POST forms
- **File uploads**: Only JPG/PNG, max 5MB, randomized filenames (UUID)
- **IDOR protection**:
  - Citizens can only access their own issues
  - Local authorities filtered by jurisdiction district
  - MINALOC sees only MINALOC-level issues
  - President sees only PRESIDENT-level issues
- **Input validation**: Min-length checks, email uniqueness, category/status enum validation

---

## API Routes Summary

| Method | Path | Who |
|---|---|---|
| GET/POST | `/register`, `/login` | Public |
| GET | `/logout` | Authenticated |
| GET/POST | `/issues/new` | CITIZEN |
| GET | `/issues` | CITIZEN |
| GET | `/issues/{id}` | CITIZEN (own issues only) |
| POST | `/issues/{id}/feedback` | CITIZEN |
| GET | `/authority/issues` | AUTH roles |
| GET | `/authority/issues/{id}` | AUTH roles |
| POST | `/authority/issues/{id}/respond` | AUTH roles |
| POST | `/authority/issues/{id}/status` | AUTH roles |
| GET/POST | `/admin/users/*` | SYS_ADMIN |
| GET/POST | `/admin/categories/*` | SYS_ADMIN |
| GET | `/admin/reports` | SYS_ADMIN |
| POST | `/admin/run-sla-check` | SYS_ADMIN |
| GET | `/admin/audit` | SYS_ADMIN |

---

## Database Indexes

The following indexes are defined for performance with 50+ concurrent users:

```sql
INDEX ix_issue_level_status (current_level, current_status)
INDEX ix_issue_level_entered (level_entered_at)
INDEX ix_auth_response_issue_level_created (issue_id, level, created_at)
INDEX ix_status_update_issue_created (issue_id, created_at)
INDEX ix_escalation_issue_created (issue_id, created_at)
```

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `APP_HOST` | App bind host | 0.0.0.0 |
| `APP_PORT` | App bind port | 8000 |
| `DATABASE_URL` | MySQL connection string | (see .env.example) |
| `APP_SECRET_KEY` | Session signing key | change-this! |
| `APP_ENV` | `development` or `production` | development |
| `UPLOAD_DIR` | Upload storage path | app/static/uploads |
| `MAX_UPLOAD_SIZE_MB` | Max file size | 5 |
| `SLA_DAYS` | Days before SLA escalation | 30 |

---

## Docker Troubleshooting

- Warning: `the attribute version is obsolete`
  - Cause: Docker Compose v2 ignores top-level `version`.
  - Current state: safe to ignore.
  - Optional cleanup: remove `version: "3.9"` from `docker-compose.yml` to silence the warning.

---

## Running Alembic Migrations (optional for production)

```bash
# Generate migration after model changes
alembic revision --autogenerate -m "describe change"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

In development, tables are auto-created by `Base.metadata.create_all()` on startup.

---

## Low-Bandwidth Optimizations

- All pages served as server-rendered HTML (no SPA overhead)
- Images compressed client-side limit: 5MB max accepted
- Bootstrap served from CDN with browser caching
- No inline base64 images
- Tables paginated/limited (audit log: 500 entries max per load)
