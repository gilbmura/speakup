@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  SpeakUp — Start application (Windows)
REM ─────────────────────────────────────────────────────────────────────────────

if not exist .venv (
    echo ERROR: Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo Starting SpeakUp on http://localhost:8000 ...
echo Press Ctrl+C to stop.
echo.

.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload
