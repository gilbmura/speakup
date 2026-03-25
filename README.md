# SpeakUp — Community Issue Reporting and Tracking Platform

A production-ready MVP for local governance in Africa. Citizens report issues, authorities respond, and a full escalation chain ensures accountability from Local Authority through MINALOC to the President's Office.

---

## Note on testing and local setup

This project was **tested end-to-end using Docker only**. The **Windows, non-Docker** instructions (`setup.bat`, `run.bat`, local MySQL, and virtual environment steps) are included because they describe a path that can be followed on a typical Windows machine; they are **not** documented as having received the same level of verification as the Docker workflow. Prefer **Docker** when you want the environment that matches how the application was actually run and tested.

---

## Table of contents

1. [Note on testing and local setup](#note-on-testing-and-local-setup)
2. [What Docker runs](#what-docker-runs)
3. [Prerequisites](#prerequisites)
4. [Docker: first-time setup](#docker-first-time-setup)
5. [Test users (seed.py)](#test-users-created-by-seedpy)
6. [Useful Docker commands](#useful-docker-commands)
7. [Configuration and secrets](#configuration-and-secrets)
8. [Troubleshooting: Docker build](#troubleshooting-docker-build-failures)
9. [Troubleshooting: runtime and ports](#troubleshooting-container-starts-but-app-fails)
10. [Local development without Docker](#local-development-without-docker)
11. [Production and security notes](#production-and-security-notes)
12. [Project structure](#project-structure)
13. [How escalation works](#how-escalation-works)
14. [Anonymity and identity visibility](#anonymity-and-identity-visibility)
15. [Security features](#security-features)
16. [API routes summary](#api-routes-summary)
17. [Database indexes](#database-indexes)
18. [Environment variables (reference)](#environment-variables-reference)
19. [Alembic migrations](#running-alembic-migrations-optional-for-production)
20. [Low-bandwidth optimizations](#low-bandwidth-optimizations)

---

## What Docker runs

| Component | Image / build | Host port | Purpose |
|-----------|-----------------|-----------|---------|
| `db` | `mysql:8.0` | **3307** maps to container 3306 | MySQL database; persistent data in named volume `speakup_mysql_data` |
| `app` | Built from `Dockerfile` (Python 3.11) | **8000** | FastAPI and Uvicorn |

**Startup order:** The `app` service waits until `db` passes its healthcheck (`mysqladmin ping`). The app container runs `seed.py` once, then starts Uvicorn. Tables are also created at import time via SQLAlchemy `Base.metadata.create_all()` in `app/main.py` (development-style bootstrap; production deployments should use Alembic migrations).

**Uploads:** `docker-compose.yml` mounts a named volume at `app/static/uploads` inside the container so uploaded images survive container restarts (this is not bind-mounted to your host by default).

---

## Prerequisites

1. **Docker Engine** and **Docker Compose** v2 (Docker Desktop on Windows or macOS includes both).
2. **Host ports available:** `8000` (web) and optionally `3307` (MySQL from the host). If another process uses them, change the left side of the port mappings in `docker-compose.yml` or stop the conflicting service.
3. Sufficient disk space and RAM for MySQL and the Python app (Docker Desktop defaults are usually enough for local development).

---

## Docker: first-time setup

1. Open a terminal in the project root (the directory that contains `docker-compose.yml` and `Dockerfile`).

2. Ensure the Docker daemon is running (Docker Desktop started; on Linux, `docker info` should succeed).

3. Build images and start containers:

   ```bash
   docker compose up --build
   ```

   To run in the background:

   ```bash
   docker compose up --build -d
   ```

4. When the database is healthy and the app is listening, open **http://localhost:8000** in a browser.

5. **Seeding:** `seed.py` runs automatically every time the `app` container starts (before Uvicorn). It is intended to be safe to run repeatedly (idempotent seeding of categories and default users).

---

## Test users (created by seed.py)

| Role | Email | Password |
|------|-------|----------|
| SYS_ADMIN | admin@speakup.rw | Admin123! |
| LOCAL_AUTHORITY (Gasabo) | local@speakup.rw | Local123! |
| MINALOC_OFFICER | minaloc@speakup.rw | Minaloc123! |
| PRESIDENT_OFFICE_OFFICER | presoffice@speakup.rw | Pres123! |
| CITIZEN (demo) | citizen@speakup.rw | Citizen123! |

Change all passwords before any real deployment.

---

## Useful Docker commands

```bash
docker compose ps
docker compose logs -f app
docker compose logs -f db
docker compose down
```

Stop containers and remove named volumes (wipes database and upload volume data):

```bash
docker compose down -v
```

Rebuild after changing `Dockerfile` or `requirements.txt`:

```bash
docker compose build --no-cache app
docker compose up
```

---

## Configuration and secrets

### Values in `docker-compose.yml`

The `app` service sets environment variables directly (not only from a `.env` file inside the image):

- **`DATABASE_URL`** must match the MySQL user, password, host `db` (the Compose service name), and database name defined for the `db` service.
- Default DB user in Compose: `speakup` / `speakup123`, database `speakup`. Root password for the MySQL image is `rootpassword` unless you change it.

If you change `MYSQL_USER`, `MYSQL_PASSWORD`, or `MYSQL_DATABASE` under `db`, you must update **`DATABASE_URL`** on the `app` service to match.

### `APP_SECRET_KEY`

The compose file includes a placeholder `APP_SECRET_KEY`. For anything beyond local throwaway use, replace it with a long random string and keep it private.

### `.env` and `app/config.py`

`app/config.py` loads variables with `python-dotenv` from a `.env` file **if present**. Docker Compose injects variables into the container, so a `.env` file is not required inside the image for Docker runs. `.env` is mainly for non-Docker local development. See `.env.example` for variable names.

---

## Troubleshooting: Docker build failures

### `apt-get update` or `apt-get install` errors

- **Cause:** Network issues, proxy, or blocked package mirrors.
- **Actions:** Retry the build; check VPN or proxy settings; on corporate networks configure Docker proxy settings.

### `pip install` fails (timeout, SSL, hash mismatch)

- **Cause:** Network or PyPI access problems.
- **Actions:** Retry; check firewall; try a stable connection or different network.

### Compiler or wheel build errors (e.g. Pillow)

- **Cause:** Native extensions need build tools. The `Dockerfile` installs `gcc` and related packages.
- **Actions:** Keep `apt-get` dependencies aligned with `requirements.txt`. Do not remove build tools unless you rely on prebuilt wheels for your platform.

### `COPY` or `requirements.txt` not found

- **Cause:** Build context is not the directory containing `Dockerfile` and `requirements.txt`.
- **Actions:** Run `docker compose build` from the project root where `docker-compose.yml` lives.

---

## Troubleshooting: container starts but app fails

### App container exits immediately

- **Check:** `docker compose logs app`
- **Typical causes:** `seed.py` or import-time code throws (wrong `DATABASE_URL`, DB unreachable). `depends_on` with `service_healthy` should wait for MySQL; if the healthcheck fails, inspect `docker compose logs db`.

### Cannot connect to MySQL / connection refused

- **From inside the app container:** `DATABASE_URL` must use host **`db`**, not `localhost`.
- **Credentials:** User, password, and database name in `DATABASE_URL` must match the running MySQL instance.

### Database healthcheck never succeeds

- **Check:** `docker compose logs db` for MySQL errors.
- **Cause:** Mismatch between healthcheck credentials and actual MySQL users. The healthcheck uses `speakup` / `speakup123`; these must match the first-time initialization (changing env vars after a volume already exists does not change existing MySQL users without manual steps).

---

## Troubleshooting: host and port issues

### Port 8000 already in use

- **Actions:** Stop the other process, or change the mapping in `docker-compose.yml` to e.g. `"8080:8000"` and open `http://localhost:8080`.

### Port 3307 conflicts

- **Actions:** Change `"3307:3306"` to another free host port, e.g. `"3308:3306"`.

### Browser cannot reach `localhost:8000` (Windows)

- **Actions:** Confirm Docker Desktop is running; try `http://127.0.0.1:8000`; check Windows Firewall; ensure WSL2 / Docker networking is healthy if applicable.

### Compose warning: `the attribute version is obsolete`

- Docker Compose v2 may warn that top-level `version:` is ignored.
- **Actions:** Safe to ignore, or remove the `version:` line from `docker-compose.yml` to silence the warning.

---

## Local development without Docker

This section complements the [note on testing and local setup](#note-on-testing-and-local-setup): Docker is the verified path; the steps below are for developers who prefer a native Windows (or similar) install using commands and batch files that are known to be workable.

**Prerequisites:** Python 3.11+, MySQL 8 (installer, XAMPP, WAMP, or similar).

1. Copy `.env.example` to `.env` and set `DATABASE_URL` and `APP_SECRET_KEY` for your local MySQL (host `localhost`, port `3306` unless you changed it).
2. Create the database:

   ```sql
   CREATE DATABASE speakup CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

3. **Windows:** Run `setup.bat` to create a virtual environment and install dependencies. Then run `seed.py` and start the app with `run.bat`, or manually:

   ```bash
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   .venv\Scripts\python.exe seed.py
   .venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. Open **http://localhost:8000**

In development, tables are auto-created on application import. For production, prefer **Alembic** (`alembic upgrade head`) instead of relying only on `create_all`.

---

## Production and security notes

- Replace default MySQL passwords and `APP_SECRET_KEY` in Compose or your secrets manager.
- Set `https_only=True` on session middleware when serving behind HTTPS (`app/main.py`).
- Avoid exposing the MySQL host port publicly; bind to localhost only or omit the port mapping if only the app container needs the database.

---

## Project structure

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
│       └── uploads/      # Uploaded images (created at runtime if missing)
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

## How escalation works

Issues follow a three-level hierarchy: **LOCAL → MINALOC → PRESIDENT**.

### Citizen-driven escalation

1. Authority marks an issue **Resolved** at LOCAL level.
2. Citizen sees a feedback panel with **Satisfied** or **Not Resolved**.
3. If **Not Resolved**, the issue escalates to MINALOC level.
4. After MINALOC resolves, the citizen sees **Satisfied** or **Not Fair**.
5. If **Not Fair**, the issue escalates to PRESIDENT (highest level; no further escalation).

### SLA auto-escalation (runs daily at 02:00 UTC)

- If there is no `AuthorityResponse` at the current level for **30+ days** since the issue entered that level, the system auto-escalates.
- If the issue is at PRESIDENT and there is still no action after 30 days, it is flagged **OVERDUE**.
- Admin can trigger an SLA check manually: **Admin → Reports → Run SLA Check**.

The SLA timer resets whenever an issue moves to a new level (`level_entered_at` is updated).

---

## Anonymity and identity visibility

When a citizen submits an issue with **Submit Anonymously** checked:

| Viewer Role | Can see identity? |
|-------------|-------------------|
| LOCAL_AUTHORITY | Never |
| MINALOC_OFFICER | When issue is at MINALOC level or higher, or citizen marked Satisfied |
| PRESIDENT_OFFICE_OFFICER | When issue is at PRESIDENT level, or citizen marked Satisfied |
| SYS_ADMIN | Always |

This is enforced in the backend (`services.can_view_identity()`) and in templates (conditional rendering).

For **non-anonymous** issues, all roles see the reporter identity in line with normal rules.

---

## Security features

- **Passwords:** bcrypt via passlib
- **Sessions:** Signed cookie sessions via Starlette SessionMiddleware (8-hour TTL)
- **CSRF:** Token in session plus hidden form field on POST forms
- **File uploads:** JPG/PNG only, max 5MB, randomized filenames (UUID)
- **IDOR protection:** Citizens only their own issues; local authorities filtered by jurisdiction; MINALOC and President office scopes enforced
- **Input validation:** Min-length checks, email uniqueness, category/status validation

---

## API routes summary

| Method | Path | Who |
|--------|------|-----|
| GET/POST | `/register`, `/login` | Public |
| GET | `/logout` | Authenticated |
| GET/POST | `/issues/new` | CITIZEN |
| GET | `/issues` | CITIZEN |
| GET | `/issues/{id}` | CITIZEN (own issues only) |
| POST | `/issues/{id}/feedback` | CITIZEN |
| GET | `/authority/issues` | Authority roles |
| GET | `/authority/issues/{id}` | Authority roles |
| POST | `/authority/issues/{id}/respond` | Authority roles |
| POST | `/authority/issues/{id}/status` | Authority roles |
| GET/POST | `/admin/users/*` | SYS_ADMIN |
| GET/POST | `/admin/categories/*` | SYS_ADMIN |
| GET | `/admin/reports` | SYS_ADMIN |
| POST | `/admin/run-sla-check` | SYS_ADMIN |
| GET | `/admin/audit` | SYS_ADMIN |

---

## Database indexes

Indexes defined for performance with concurrent users:

```sql
INDEX ix_issue_level_status (current_level, current_status)
INDEX ix_issue_level_entered (level_entered_at)
INDEX ix_auth_response_issue_level_created (issue_id, level, created_at)
INDEX ix_status_update_issue_created (issue_id, created_at)
INDEX ix_escalation_issue_created (issue_id, created_at)
```

---

## Environment variables (reference)

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_HOST` | App bind host | 0.0.0.0 |
| `APP_PORT` | App bind port | 8000 |
| `DATABASE_URL` | MySQL SQLAlchemy URL | See `.env.example` |
| `APP_SECRET_KEY` | Session signing key | Must be set in production |
| `APP_ENV` | `development` or `production` | development |
| `UPLOAD_DIR` | Upload storage path | app/static/uploads |
| `MAX_UPLOAD_SIZE_MB` | Max file size (MB) | 5 |
| `SLA_DAYS` | Days before SLA escalation | 30 |

---

## Running Alembic migrations (optional for production)

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
alembic downgrade -1
```

In development, tables are also created by `Base.metadata.create_all()` on startup.

---

## Low-bandwidth optimizations

- Server-rendered HTML (no SPA bundle required for core UI)
- Upload size capped at 5MB
- Bootstrap loaded from CDN with browser caching
- No inline base64 images in templates
- Audit log and similar views limited (e.g. 500 entries per load)
