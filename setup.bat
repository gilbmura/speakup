@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  SpeakUp — Windows Local Setup Script (no Docker)
REM  Run this once to set up your local Python environment
REM ─────────────────────────────────────────────────────────────────────────────

echo.
echo ============================================
echo   SpeakUp — Local Setup for Windows
echo ============================================
echo.

REM 1. Create virtual environment
echo [1/5] Creating Python virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo ERROR: Python not found or venv creation failed.
    echo Make sure Python 3.11+ is installed and in your PATH.
    pause
    exit /b 1
)

REM 2. Activate venv
echo [2/5] Activating virtual environment...
call .venv\Scripts\activate.bat

REM 3. Install dependencies
echo [3/5] Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

REM 4. Create .env from example
echo [4/5] Setting up .env file...
if not exist .env (
    copy .env.example .env
    echo   .env created. IMPORTANT: Edit .env and set your DATABASE_URL!
) else (
    echo   .env already exists, skipping.
)

REM 5. Create uploads dir
echo [5/5] Creating uploads directory...
if not exist app\static\uploads mkdir app\static\uploads

echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo NEXT STEPS:
echo   1. Edit .env and set your MySQL credentials:
echo      DATABASE_URL=mysql+pymysql://root:YOURPASSWORD@localhost:3306/speakup
echo.
echo   2. Create the MySQL database:
echo      mysql -u root -p -e "CREATE DATABASE speakup CHARACTER SET utf8mb4;"
echo.
echo   3. Run the seed script:
echo      .venv\Scripts\python.exe seed.py
echo.
echo   4. Start the application:
echo      run.bat
echo.
pause
